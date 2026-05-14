"""
ALOS Authentication and Authorization Package.
Provides Role-Based Access Control (RBAC) and API key management.
"""

from .role_definitions import Role, Permission, RoleDefinition, get_role_permissions, has_permission
from .api_key_manager import APIKeyManager, get_api_key_manager
from .rbac import RBACManager, get_rbac_manager, require_memory_read, require_memory_write, require_session_read, require_session_write, require_run_create, require_run_read, require_run_write, require_patch_read, require_patch_write, require_settings_read, require_settings_write, require_user_read, require_user_write, require_apikey_read, require_apikey_write, require_audit_read, require_admin_access

__all__ = [
    # Role definitions
    "Role",
    "Permission", 
    "RoleDefinition",
    "get_role_permissions",
    "has_permission",
    
    # API key management
    "APIKeyManager",
    "get_api_key_manager",
    
    # RBAC system
    "RBACManager",
    "get_rbac_manager",
    
    # Dependencies
    "require_memory_read",
    "require_memory_write",
    "require_session_read",
    "require_session_write",
    "require_run_create",
    "require_run_read",
    "require_run_write",
    "require_patch_read",
    "require_patch_write",
    "require_settings_read",
    "require_settings_write",
    "require_user_read",
    "require_user_write",
    "require_apikey_read",
    "require_apikey_write",
    "require_audit_read",
    "require_admin_access",
]