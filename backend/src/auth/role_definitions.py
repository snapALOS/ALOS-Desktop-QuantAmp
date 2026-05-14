"""
Role-Based Access Control (RBAC) role definitions for ALOS.
Defines roles, permissions, and permission mapping to API endpoints.
"""

from enum import Enum
from typing import Dict, List, Set, Optional, Union
from dataclasses import dataclass


class Role(str, Enum):
    """User roles in ALOS system."""
    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"
    AUDITOR = "auditor"


class Permission(str, Enum):
    """Granular permissions in ALOS system."""
    # Memory operations
    MEMORY_READ = "memory:read"
    MEMORY_WRITE = "memory:write"
    MEMORY_DELETE = "memory:delete"
    MEMORY_ADMIN = "memory:admin"
    
    # Session operations
    SESSION_READ = "session:read"
    SESSION_WRITE = "session:write"
    SESSION_DELETE = "session:delete"
    
    # Run operations
    RUN_CREATE = "run:create"
    RUN_READ = "run:read"
    RUN_UPDATE = "run:update"
    RUN_DELETE = "run:delete"
    RUN_EXECUTE = "run:execute"
    
    # Patch operations
    PATCH_READ = "patch:read"
    PATCH_WRITE = "patch:write"
    PATCH_APPLY = "patch:apply"
    PATCH_DELETE = "patch:delete"
    
    # Settings operations
    SETTINGS_READ = "settings:read"
    SETTINGS_WRITE = "settings:write"
    
    # User management
    USER_READ = "user:read"
    USER_WRITE = "user:write"
    USER_DELETE = "user:delete"
    USER_ADMIN = "user:admin"
    
    # API key management
    APIKEY_READ = "apikey:read"
    APIKEY_WRITE = "apikey:write"
    APIKEY_DELETE = "apikey:delete"
    
    # Audit operations
    AUDIT_READ = "audit:read"
    AUDIT_ADMIN = "audit:admin"


@dataclass
class RoleDefinition:
    """Definition of a role with its permissions and description."""
    name: str
    description: str
    permissions: Set[Permission]
    inherits_from: List[Role] = None  # Roles this role inherits permissions from


# Role definitions with permission mappings
ROLE_DEFINITIONS: Dict[Role, RoleDefinition] = {
    Role.ADMIN: RoleDefinition(
        name="Administrator",
        description="Full system access with user and API key management capabilities",
        permissions={
            # Full memory access
            Permission.MEMORY_READ, Permission.MEMORY_WRITE, Permission.MEMORY_DELETE, Permission.MEMORY_ADMIN,
            # Full session access
            Permission.SESSION_READ, Permission.SESSION_WRITE, Permission.SESSION_DELETE,
            # Full run access
            Permission.RUN_CREATE, Permission.RUN_READ, Permission.RUN_UPDATE, Permission.RUN_DELETE, Permission.RUN_EXECUTE,
            # Full patch access
            Permission.PATCH_READ, Permission.PATCH_WRITE, Permission.PATCH_APPLY, Permission.PATCH_DELETE,
            # Full settings access
            Permission.SETTINGS_READ, Permission.SETTINGS_WRITE,
            # Full user management
            Permission.USER_READ, Permission.USER_WRITE, Permission.USER_DELETE, Permission.USER_ADMIN,
            # Full API key management
            Permission.APIKEY_READ, Permission.APIKEY_WRITE, Permission.APIKEY_DELETE,
            # Audit access
            Permission.AUDIT_READ, Permission.AUDIT_ADMIN,
        },
        inherits_from=[]
    ),
    
    Role.USER: RoleDefinition(
        name="Standard User",
        description="Standard user with read/write access to own data and limited admin functions",
        permissions={
            # Own memory operations
            Permission.MEMORY_READ, Permission.MEMORY_WRITE,
            # Own session operations
            Permission.SESSION_READ, Permission.SESSION_WRITE,
            # Own run operations
            Permission.RUN_CREATE, Permission.RUN_READ, Permission.RUN_UPDATE, Permission.RUN_EXECUTE,
            # Patch operations (own patches)
            Permission.PATCH_READ, Permission.PATCH_WRITE, Permission.PATCH_APPLY,
            # Settings (read own, write limited)
            Permission.SETTINGS_READ,
            # Own API key management
            Permission.APIKEY_READ, Permission.APIKEY_WRITE,
            # Basic audit (own activities)
            Permission.AUDIT_READ,
        },
        inherits_from=[]
    ),
    
    Role.VIEWER: RoleDefinition(
        name="Viewer",
        description="Read-only access to system resources",
        permissions={
            # Read-only memory access
            Permission.MEMORY_READ,
            # Read-only session access
            Permission.SESSION_READ,
            # Read-only run access
            Permission.RUN_READ,
            # Read-only patch access
            Permission.PATCH_READ,
            # Read-only settings
            Permission.SETTINGS_READ,
            # Read own API keys (but cannot create/modify)
            Permission.APIKEY_READ,
            # Read own audit logs
            Permission.AUDIT_READ,
        },
        inherits_from=[]
    ),
    
    Role.AUDITOR: RoleDefinition(
        name="Auditor",
        description="Read-only access focused on audit trails and compliance",
        permissions={
            # Read-only memory access (for auditing)
            Permission.MEMORY_READ,
            # Read-only session access
            Permission.SESSION_READ,
            # Read-only run access
            Permission.RUN_READ,
            # Read-only patch access
            Permission.PATCH_READ,
            # Read-only settings
            Permission.SETTINGS_READ,
            # No user management
            # Full audit access
            Permission.AUDIT_READ,
            # Can read other users' audit logs (limited)
        },
        inherits_from=[Role.VIEWER]  # Inherits viewer permissions
    ),
}


def get_role_permissions(role: Role) -> Set[Permission]:
    """
    Get all permissions for a role, including inherited permissions.
    
    Args:
        role: The role to get permissions for
        
    Returns:
        Set of permissions for the role
    """
    if role not in ROLE_DEFINITIONS:
        return set()
    
    definition = ROLE_DEFINITIONS[role]
    permissions = set(definition.permissions)
    
    # Add inherited permissions
    if definition.inherits_from:
        for inherited_role in definition.inherits_from:
            permissions.update(get_role_permissions(inherited_role))
    
    return permissions


def has_permission(role: Role, permission: Permission) -> bool:
    """
    Check if a role has a specific permission.
    
    Args:
        role: The role to check
        permission: The permission to check for
        
    Returns:
        True if role has permission, False otherwise
    """
    return permission in get_role_permissions(role)


def get_role_description(role: Role) -> str:
    """
    Get the description for a role.
    
    Args:
        role: The role to get description for
        
    Returns:
        Role description string
    """
    if role in ROLE_DEFINITIONS:
        return ROLE_DEFINITIONS[role].description
    return "Unknown role"


def get_all_roles() -> List[Role]:
    """
    Get all defined roles.
    
    Returns:
        List of all roles
    """
    return list(ROLE_DEFINITIONS.keys())


# API endpoint to permission mapping
ENDPOINT_PERMISSION_MAP = {
    # Memory endpoints
    "GET:/api/memory/search": Permission.MEMORY_READ,
    "POST:/api/memory/add": Permission.MEMORY_WRITE,
    "DELETE:/api/memory/{memory_id}": Permission.MEMORY_DELETE,
    "GET:/api/memory/session": Permission.MEMORY_READ,
    
    # Session endpoints
    "POST:/api/sessions": Permission.SESSION_WRITE,
    "GET:/api/sessions": Permission.SESSION_READ,
    "GET:/api/sessions/{session_id}": Permission.SESSION_READ,
    "PUT:/api/sessions/{session_id}": Permission.SESSION_WRITE,
    "DELETE:/api/sessions/{session_id}": Permission.SESSION_DELETE,
    
    # Run endpoints
    "POST:/api/runs": Permission.RUN_CREATE,
    "GET:/api/runs": Permission.RUN_READ,
    "GET:/api/runs/{run_id}": Permission.RUN_READ,
    "PUT:/api/runs/{run_id}": Permission.RUN_UPDATE,
    "DELETE:/api/runs/{run_id}": Permission.RUN_DELETE,
    "POST:/api/runs/{run_id}/cancel": Permission.RUN_UPDATE,
    "POST:/api/runs/{run_id}/replay": Permission.RUN_READ,
    
    # Patch endpoints
    "GET:/api/patches": Permission.PATCH_READ,
    "POST:/api/patches/propose": Permission.PATCH_WRITE,
    "POST:/api/patches/{patch_id}/apply": Permission.PATCH_APPLY,
    "POST:/api/patches/{patch_id}/reject": Permission.PATCH_WRITE,
    
    # Settings endpoints
    "GET:/api/settings": Permission.SETTINGS_READ,
    "PUT:/api/api/settings": Permission.SETTINGS_WRITE,
    
    # Auth endpoints (generally accessible)
    "POST:/auth/login": None,  # No permission required - authentication endpoint
    "POST:/auth/apikey": None,  # No permission required - authentication endpoint
    "POST:/auth/register": Permission.USER_ADMIN,
    "GET:/auth/me": None,  # Returns info about authenticated user
    "POST:/auth/apikey/generate": Permission.APIKEY_WRITE,
    "POST:/auth/apikey/revoke": Permission.APIKEY_DELETE,
    
    # Admin endpoints (future)
    "GET:/admin/users": Permission.USER_ADMIN,
    "POST:/admin/users": Permission.USER_ADMIN,
    "GET:/admin/users/{user_id}": Permission.USER_READ,
    "PUT:/admin/users/{user_id}": Permission.USER_WRITE,
    "DELETE:/admin/users/{user_id}": Permission.USER_DELETE,
    "GET:/admin/apikeys": Permission.APIKEY_READ,
    "POST:/admin/apikeys": Permission.APIKEY_WRITE,
    "DELETE:/admin/apikeys/{key_id}": Permission.APIKEY_DELETE,
    "GET:/admin/audit-log": Permission.AUDIT_READ,
}


def get_required_permission(method: str, path: str) -> Optional[Permission]:
    """
    Get the required permission for an API endpoint.
    
    Args:
        method: HTTP method (GET, POST, PUT, DELETE)
        path: API endpoint path
        
    Returns:
        Required permission or None if no authentication required
    """
    key = f"{method}:{path}"
    return ENDPOINT_PERMISSION_MAP.get(key)

