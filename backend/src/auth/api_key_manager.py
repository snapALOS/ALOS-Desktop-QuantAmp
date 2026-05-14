"""
API Key management for ALOS RBAC system.
Handles generation, validation, rotation, and secure storage of API keys.
"""

import os
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict

from src.api.database import get_db_connection
from src.auth.role_definitions import Role, Permission
from src.core.config import system_logger


def _sha256(value: str) -> str:
    """SHA256 hash for API key storage and lookup. API keys are strong random
    values so SHA256 is sufficient — bcrypt is unnecessary here."""
    return hashlib.sha256(value.encode()).hexdigest()


class APIKeyManager:
    """Manages API keys for ALOS users."""
    
    def __init__(self):
        self._ensure_tables()
    
    def _ensure_tables(self):
        """Ensure the required tables exist for API key and user management."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Users table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE,
                    password_hash TEXT,
                    role TEXT NOT NULL DEFAULT 'viewer',
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP,
                    failed_login_attempts INTEGER DEFAULT 0,
                    locked_until TIMESTAMP
                )
            """)
            
            # API keys table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    key_hash TEXT NOT NULL,
                    name TEXT NOT NULL,
                    expires_at TIMESTAMP,
                    last_used_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    revoked BOOLEAN NOT NULL DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
            
            # User roles and permissions table (for future extension)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_roles (
                    id TEXT PRIMARY KEY,
                    role_name TEXT UNIQUE NOT NULL,
                    permissions TEXT,  -- JSON string of permissions
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Audit log table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    action TEXT NOT NULL,
                    resource TEXT,
                    outcome TEXT NOT NULL,  -- success/failure
                    ip_address TEXT,
                    user_agent TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
                )
            """)
            
            # Session to user mapping (for backward compatibility with existing sessions)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS session_users (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
                )
            """)
            
            # Create indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_user_id ON api_keys(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash ON api_keys(key_hash)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_user_id ON audit_log(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_session_users_session_id ON session_users(session_id)")
            
            conn.commit()
    
    def generate_api_key(self) -> str:
        """
        Generate a secure random API key.
        
        Returns:
            A secure random API key string
        """
        # Generate a URL-safe key with prefix for easy identification
        random_part = secrets.token_urlsafe(32)
        return f"alos_{random_part}"
    
    def hash_api_key(self, api_key: str) -> str:
        """Hash an API key for secure storage using SHA256."""
        return _sha256(api_key)

    def verify_api_key(self, plain_key: str, hashed_key: str) -> bool:
        """Verify a plain API key against its stored hash."""
        return _sha256(plain_key) == hashed_key
    
    def create_api_key(self, user_id: str, name: str, expires_in_days: Optional[int] = None) -> Tuple[str, str]:
        """
        Create a new API key for a user.
        
        Args:
            user_id: The user ID to create the key for
            name: A descriptive name for the API key
            expires_in_days: Optional expiration in days (None for no expiration)
            
        Returns:
            Tuple of (api_key_id, plain_api_key)
            
        Raises:
            ValueError: If user_id is invalid
        """
        # Validate user exists
        if not self._user_exists(user_id):
            raise ValueError(f"User {user_id} does not exist")
        
        # Generate key and hash it deterministically
        plain_key = self.generate_api_key()
        key_hash = _sha256(plain_key)
        
        # Calculate expiration
        expires_at = None
        if expires_in_days is not None:
            expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
        
        # Store in database
        key_id = secrets.token_urlsafe(16)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO api_keys (id, user_id, key_hash, name, expires_at)
                VALUES (?, ?, ?, ?, ?)
            """, (key_id, user_id, key_hash, name, expires_at))
            conn.commit()
        
        # Log audit event
        self._log_audit_event(
            user_id=user_id,
            action="api_key_create",
            resource=f"api_key:{key_id}",
            outcome="success"
        )
        
        return key_id, plain_key

    def has_any_users(self) -> bool:
        """Return True once the local auth database has been initialized by a user."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM users LIMIT 1")
            return cursor.fetchone() is not None

    def original_admin_bootstrap_status(self) -> Dict:
        """Public-safe first-run status for the local original-admin flow."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = int(cursor.fetchone()[0])
            cursor.execute(
                "SELECT COUNT(*) FROM users WHERE role = ? AND is_active = 1",
                (Role.ADMIN.value,),
            )
            active_admins = int(cursor.fetchone()[0])

        return {
            "users_exist": total_users > 0,
            "active_admins": active_admins,
            "can_bootstrap": total_users == 0,
        }

    def create_original_admin(
        self,
        username: str = "admin",
        key_name: Optional[str] = None,
    ) -> Dict:
        """
        Create the first local admin user and one API key.

        This is deliberately limited to an empty users table. Recovery for an
        existing install must be an authenticated or explicitly audited flow,
        not a public reset endpoint.
        """
        clean_username = (username or "admin").strip() or "admin"
        if len(clean_username) > 48:
            raise ValueError("Username must be 48 characters or fewer")

        admin_id = "root_admin"
        api_key_id = secrets.token_urlsafe(16)
        plain_key = self.generate_api_key()
        key_hash = _sha256(plain_key)
        resolved_key_name = key_name or (
            f"Original Admin Key ({datetime.utcnow().strftime('%Y-%m-%d %H:%M')})"
        )

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute("SELECT 1 FROM users LIMIT 1")
            if cursor.fetchone() is not None:
                conn.rollback()
                raise ValueError("Original admin has already been configured")

            cursor.execute(
                """
                INSERT INTO users (id, username, role, is_active)
                VALUES (?, ?, ?, ?)
                """,
                (admin_id, clean_username, Role.ADMIN.value, 1),
            )
            cursor.execute(
                """
                INSERT INTO api_keys (id, user_id, key_hash, name, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (api_key_id, admin_id, key_hash, resolved_key_name, None),
            )
            cursor.execute(
                """
                INSERT INTO audit_log (id, user_id, action, resource, outcome, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    secrets.token_urlsafe(16),
                    admin_id,
                    "original_admin_create",
                    f"api_key:{api_key_id}",
                    "success",
                    "local",
                    "alos-first-run",
                ),
            )
            conn.commit()

        return {
            "api_key_id": api_key_id,
            "api_key": plain_key,
            "user": {
                "user_id": "root_admin",
                "username": clean_username,
                "role": Role.ADMIN.value,
            },
        }
    
    def validate_api_key(self, api_key: str) -> Optional[Dict]:
        """
        Validate an API key and return associated user info.
        Uses SHA256 for deterministic lookup, then checks lockout and expiry.
        """
        if not api_key or not api_key.startswith("alos_"):
            return None

        key_hash = _sha256(api_key)

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ak.id, ak.user_id, ak.name, ak.expires_at, ak.revoked,
                       u.username, u.role, u.is_active
                FROM api_keys ak
                LEFT JOIN users u ON ak.user_id = u.id
                WHERE ak.key_hash = ? AND ak.revoked = 0
            """, (key_hash,))
            row = cursor.fetchone()

            if not row:
                self._log_audit_event(None, "api_key_validate", "unknown", "failure")
                return None

            key_id, user_id, name, expires_at, revoked, username, role, is_active = row

            # root_admin is a synthetic superuser not in the users table
            if user_id == "root_admin":
                username = username or "root_admin"
                role = role or "admin"
                is_active = 1

            # Check user is active
            if not is_active:
                self._log_audit_event(user_id, "api_key_validate", f"api_key:{key_id}", "failure")
                return None

            # Check brute-force lockout (real users only)
            if user_id and user_id != "root_admin":
                cursor.execute(
                    "SELECT locked_until FROM users WHERE id = ?", (user_id,)
                )
                lock_row = cursor.fetchone()
                if lock_row and lock_row[0]:
                    locked_until = datetime.fromisoformat(lock_row[0])
                    if locked_until > datetime.utcnow():
                        self._log_audit_event(user_id, "api_key_validate", f"api_key:{key_id}", "failure")
                        return None

            # Check expiration
            if expires_at:
                expires_dt = datetime.fromisoformat(expires_at) if isinstance(expires_at, str) else expires_at
                if expires_dt < datetime.utcnow():
                    self._log_audit_event(user_id, "api_key_validate", f"api_key:{key_id}", "failure")
                    return None

            # Success — update last used and reset failed attempts
            cursor.execute(
                "UPDATE api_keys SET last_used_at = CURRENT_TIMESTAMP WHERE id = ?", (key_id,)
            )
            if user_id and user_id != "root_admin":
                cursor.execute(
                    "UPDATE users SET failed_login_attempts = 0, locked_until = NULL WHERE id = ?",
                    (user_id,)
                )
            conn.commit()

            self._log_audit_event(user_id, "api_key_validate", f"api_key:{key_id}", "success")

            return {
                "id": key_id,
                "user_id": user_id,
                "username": username or user_id,
                "role": role,
                "name": name,
                "expires_at": expires_at
            }

    MAX_FAILED_ATTEMPTS = 10
    LOCKOUT_MINUTES = 15

    def record_failed_attempt(self, user_id: str) -> None:
        """Increment failed login attempts; lock account after MAX_FAILED_ATTEMPTS."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users
                SET failed_login_attempts = failed_login_attempts + 1,
                    locked_until = CASE
                        WHEN failed_login_attempts + 1 >= ?
                        THEN datetime('now', '+15 minutes')
                        ELSE locked_until
                    END
                WHERE id = ?
            """, (self.MAX_FAILED_ATTEMPTS, user_id))
            conn.commit()
    
    def revoke_api_key(self, key_id: str, user_id: str) -> bool:
        """
        Revoke an API key.
        
        Args:
            key_id: The API key ID to revoke
            user_id: The user ID (for ownership verification)
            
        Returns:
            True if revoked, False otherwise
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE api_keys SET revoked = 1 
                WHERE id = ? AND user_id = ?
            """, (key_id, user_id))
            conn.commit()
            
            if cursor.rowcount > 0:
                # Log audit event
                self._log_audit_event(
                    user_id=user_id,
                    action="api_key_revoke",
                    resource=f"api_key:{key_id}",
                    outcome="success"
                )
                return True
            else:
                return False
    
    def list_user_api_keys(self, user_id: str) -> List[Dict]:
        """
        List all API keys for a user (without exposing the actual keys).
        
        Args:
            user_id: The user ID
            
        Returns:
            List of API key metadata dictionaries
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, expires_at, last_used_at, created_at, revoked
                FROM api_keys
                WHERE user_id = ?
                ORDER BY created_at DESC
            """, (user_id,))
            rows = cursor.fetchall()
            
            keys = []
            for row in rows:
                key_id, name, expires_at, last_used_at, created_at, revoked = row
                keys.append({
                    "id": key_id,
                    "name": name,
                    "expires_at": expires_at,
                    "last_used_at": last_used_at,
                    "created_at": created_at,
                    "revoked": bool(revoked)
                })
            
            return keys
    
    def _user_exists(self, user_id: str) -> bool:
        """Check if a user exists."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM users WHERE id = ?", (user_id,))
            return cursor.fetchone() is not None
    
    def _log_audit_event(self, user_id: Optional[str], action: str, resource: str, 
                        outcome: str, ip_address: str = "unknown", user_agent: str = "unknown"):
        """Log an audit event."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO audit_log (id, user_id, action, resource, outcome, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                secrets.token_urlsafe(16),
                user_id,
                action,
                resource,
                outcome,
                ip_address,
                user_agent
            ))
            conn.commit()


# Global instance
api_key_manager = APIKeyManager()


def get_api_key_manager() -> APIKeyManager:
    """Get the global API key manager instance."""
    return api_key_manager
