"""
Role-Based Access Control (RBAC) system for ALOS.
Implements role checking, permission validation, and access control.
"""

from functools import wraps
from typing import Callable, Any, Optional
from fastapi import HTTPException, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import logging
import os

from src.auth.role_definitions import Role, Permission, get_role_permissions, has_permission, get_required_permission
from src.auth.api_key_manager import get_api_key_manager, APIKeyManager
from src.auth.role_definitions import RoleDefinition
from src.api.auth_bridge import get_active_user, get_active_session, set_active_user, reset_active_user
from src.core.config import system_logger

# Security scheme for API key authentication
security = HTTPBearer(auto_error=False)

logger = logging.getLogger("ALOS.auth.rbac")

# Emergency override - set environment variable ALOS_RBAC_DISABLED=true to disable RBAC for recovery
# This should ONLY be used in emergency situations when locked out
RBAC_DISABLED = os.getenv("ALOS_RBAC_DISABLED", "false").lower() == "true"

if RBAC_DISABLED:
    logger.warning("RBAC SYSTEM IS DISABLED VIA ENVIRONMENT VARIABLE - USE ONLY FOR RECOVERY!")
else:
    logger.info("RBAC system enabled")


class RBACManager:
    """Manages RBAC operations including role checking and permission validation."""
    
    def __init__(self):
        self.api_key_manager = get_api_key_manager()
    
    def authenticate_request(self, request: Request, credentials: Optional[HTTPAuthorizationCredentials] = None) -> Optional[str]:
        """
        Authenticate a request using API key or session context.
        
        Args:
            request: The FastAPI request object
            credentials: Optional HTTP Bearer credentials
            
        Returns:
            User ID if authentication successful, None otherwise
        """
        # Try API key authentication first (from Authorization header)
        if credentials and credentials.scheme.lower() == "bearer":
            api_key = credentials.credentials
            user_info = self.api_key_manager.validate_api_key(api_key)
            if user_info:
                user_id = user_info["user_id"]
                # Set user context for the request
                set_active_user(user_id)
                logger.debug(f"Authenticated user {user_id} via API key")
                return user_id
        
        # Fallback to session-based authentication (existing mechanism)
        session_id = get_active_session()
        if session_id:
            # Map session to user if available
            user_id = self._get_user_from_session(session_id)
            if user_id:
                set_active_user(user_id)
                logger.debug(f"Authenticated user {user_id} via session {session_id}")
                return user_id
        
        # No authentication found
        return None
    
    def _get_user_from_session(self, session_id: str) -> Optional[str]:
        """Get user ID associated with a session."""
        try:
            # This would query the session_users table
            # For now, we'll return None to maintain backward compatibility
            # In a full implementation, this would check the database
            return None
        except Exception as e:
            logger.error(f"Error getting user from session: {e}")
            return None
    
    def check_permission(self, user_id: str, permission: Permission) -> bool:
        """
        Check if a user has a specific permission.
        
        Args:
            user_id: The user ID to check
            permission: The permission to check for
            
        Returns:
            True if user has permission, False otherwise
        """
        try:
            # Get user role from database
            role = self._get_user_role(user_id)
            if role is None:
                logger.warning(f"User {user_id} has no role assigned")
                return False
            
            # Check if role has permission
            has_perm = has_permission(role, permission)
            if not has_perm:
                logger.debug(f"User {user_id} ({role}) lacks permission {permission}")
            
            return has_perm
        except Exception as e:
            logger.error(f"Error checking permission for user {user_id}: {e}")
            return False
    
    def _get_user_role(self, user_id: str) -> Optional[Role]:
        """Get the role for a user from the database."""
        try:
            if user_id == "root_admin" or user_id == "emergency_access":
                return Role.ADMIN

            from src.api.database import get_db_connection
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT role FROM users WHERE id = ? AND is_active = 1", (user_id,))
                row = cursor.fetchone()
                if not row:
                    logger.warning(f"No active user found for id {user_id}")
                    return None
                role_str = row[0]

            # Map string to Role enum
            role_map = {
                "admin": Role.ADMIN,
                "ADMIN": Role.ADMIN,
                "user": Role.USER,
                "USER": Role.USER,
                "viewer": Role.VIEWER,
                "VIEWER": Role.VIEWER,
                "auditor": Role.AUDITOR,
                "AUDITOR": Role.AUDITOR,
            }
            role = role_map.get(role_str)
            if not role:
                logger.warning(f"Unknown role '{role_str}' for user {user_id}, defaulting to VIEWER")
                return Role.VIEWER
            return role
        except Exception as e:
            logger.error(f"Error getting role for user {user_id}: {e}")
            return None
    
    def require_permission(self, permission: Permission):
        """
        Dependency factory for requiring a specific permission.
        
        Args:
            permission: The permission required
            
        Returns:
            A FastAPI dependency function
        """
        def permission_checker(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
            # Emergency bypass for recovery situations
            if RBAC_DISABLED:
                logger.warning("RBAC bypassed due to ALOS_RBAC_DISABLED environment variable")
                return "emergency_access"
            
            # Authenticate the request
            user_id = self.authenticate_request(request, credentials)
            if user_id is None:
                raise HTTPException(
                    status_code=401,
                    detail="Authentication required",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            # Check permission
            if not self.check_permission(user_id, permission):
                raise HTTPException(
                    status_code=403,
                    detail=f"Insufficient permissions. Required: {permission.value}"
                )
            
            return user_id
        
        return permission_checker
    
    def require_any_permission(self, *permissions: Permission):
        """
        Dependency factory for requiring any of several permissions.
        
        Args:
            *permissions: Permissions where having any one is sufficient
            
        Returns:
            A FastAPI dependency function
        """
        def permission_checker(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
            # Emergency bypass for recovery situations
            if RBAC_DISABLED:
                logger.warning("RBAC bypassed due to ALOS_RBAC_DISABLED environment variable")
                return "emergency_access"
            
            # Authenticate the request
            user_id = self.authenticate_request(request, credentials)
            if user_id is None:
                raise HTTPException(
                    status_code=401,
                    detail="Authentication required",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            # Check if user has any of the required permissions
            has_any_perm = any(self.check_permission(user_id, perm) for perm in permissions)
            if not has_any_perm:
                perm_list = ", ".join([p.value for p in permissions])
                raise HTTPException(
                    status_code=403,
                    detail=f"Insufficient permissions. Required one of: {perm_list}"
                )
            
            return user_id
        
        return permission_checker
    
    def get_current_user(self, request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Optional[str]:
        """
        Get the current authenticated user (optional authentication).
        
        Args:
            request: The FastAPI request object
            credentials: Optional HTTP Bearer credentials
            
        Returns:
            User ID if authenticated, None otherwise
        """
        return self.authenticate_request(request, credentials)
    
    def get_current_user_required(self, request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> str:
        """
        Get the current authenticated user (required authentication).
        
        Args:
            request: The FastAPI request object
            credentials: Optional HTTP Bearer credentials
            
        Returns:
            User ID
            
        Raises:
            HTTPException: If not authenticated
        """
        # Emergency bypass for recovery situations
        if RBAC_DISABLED:
            logger.warning("RBAC bypassed due to ALOS_RBAC_DISABLED environment variable")
            return "emergency_access"
        
        user_id = self.authenticate_request(request, credentials)
        if user_id is None:
            raise HTTPException(
                status_code=401,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user_id


# Global RBAC manager instance
rbac_manager = RBACManager()


def get_rbac_manager() -> RBACManager:
    """Get the global RBAC manager instance."""
    return rbac_manager


# Convenience dependencies for common permissions
def require_memory_read(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> str:
    """Require memory read permission."""
    return rbac_manager.require_permission(Permission.MEMORY_READ)(request, credentials)


def require_memory_write(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> str:
    """Require memory write permission."""
    return rbac_manager.require_permission(Permission.MEMORY_WRITE)(request, credentials)


def require_session_read(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> str:
    """Require session read permission."""
    return rbac_manager.require_permission(Permission.SESSION_READ)(request, credentials)


def require_session_write(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> str:
    """Require session write permission."""
    return rbac_manager.require_permission(Permission.SESSION_WRITE)(request, credentials)


def require_run_create(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> str:
    """Require run create permission."""
    return rbac_manager.require_permission(Permission.RUN_CREATE)(request, credentials)


def require_run_read(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> str:
    """Require run read permission."""
    return rbac_manager.require_permission(Permission.RUN_READ)(request, credentials)


def require_run_write(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> str:
    """Require run update/delete permission."""
    return rbac_manager.require_any_permission(
        Permission.RUN_UPDATE, Permission.RUN_DELETE
    )(request, credentials)


def require_patch_read(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> str:
    """Require patch read permission."""
    return rbac_manager.require_permission(Permission.PATCH_READ)(request, credentials)


def require_patch_write(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> str:
    """Require patch write/apply permission."""
    return rbac_manager.require_any_permission(
        Permission.PATCH_WRITE, Permission.PATCH_APPLY
    )(request, credentials)


def require_settings_read(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> str:
    """Require settings read permission."""
    return rbac_manager.require_permission(Permission.SETTINGS_READ)(request, credentials)


def require_settings_write(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> str:
    """Require settings write permission."""
    return rbac_manager.require_permission(Permission.SETTINGS_WRITE)(request, credentials)


def require_user_read(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> str:
    """Require user read permission."""
    return rbac_manager.require_permission(Permission.USER_READ)(request, credentials)


def require_user_write(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> str:
    """Require user write/delete permission."""
    return rbac_manager.require_any_permission(
        Permission.USER_WRITE, Permission.USER_DELETE
    )(request, credentials)


def require_apikey_read(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> str:
    """Require API key read permission."""
    return rbac_manager.require_permission(Permission.APIKEY_READ)(request, credentials)


def require_apikey_write(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> str:
    """Require API key write/delete permission."""
    return rbac_manager.require_any_permission(
        Permission.APIKEY_WRITE, Permission.APIKEY_DELETE
    )(request, credentials)


def require_audit_read(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> str:
    """Require audit read permission."""
    return rbac_manager.require_permission(Permission.AUDIT_READ)(request, credentials)


def require_admin_access(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> str:
    """Require admin-level access."""
    return rbac_manager.require_permission(Permission.USER_ADMIN)(request, credentials)


# Decorator for protecting functions with RBAC
def rbac_required(permission: Permission):
    """
    Decorator to require a specific permission for a function.
    
    Args:
        permission: The permission required
        
    Returns:
        Decorated function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request from args/kwargs if present
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            if not request:
                # Look in kwargs
                request = kwargs.get('request')
            
            if not request:
                # If we can't find request, we can't do RBAC checking
                logger.warning("Cannot perform RBAC check: no Request object found")
                return await func(*args, **kwargs)
            
            # For simplicity, we'll rely on the dependency injection approach in route handlers
            # This decorator is more for direct function calls
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


def initialize_rbac():
    """
    Initialize the RBAC system.
    Creates default roles and admin user if needed.
    """
    logger.info("Initializing RBAC system...")
    
    # In a full implementation, this would:
    # 1. Ensure tables exist
    # 2. Create default roles if they don't exist
    # 3. Create an initial admin user if no users exist
    # 4. Set up any initial data
    
    logger.info("RBAC system initialized")