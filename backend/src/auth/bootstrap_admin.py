#!/usr/bin/env python3
"""
ALOS RBAC Bootstrap Script
Creates admin user and master API key for initial access
"""

import os
import sys
import secrets
import sqlite3
from datetime import datetime

# Add project root to path for imports
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT_DIR)

from src.auth.api_key_manager import get_api_key_manager
from src.auth.role_definitions import Role
from src.api.database import DB_PATH
from src.core.config import USER_DATA_DIR


def bootstrap_admin():
    print("--- ALOS RBAC BOOTSTRAP ---")
    print(f"Target Database: {DB_PATH}")
    
    manager = get_api_key_manager()
    
    # 1. Ensure tables are initialized
    manager._ensure_tables()
    
    admin_id = "root_admin"
    username = "admin"
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        # 2. Check if admin user exists
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        existing_user = cursor.fetchone()
        
        if existing_user:
            admin_id = existing_user[0]
            print(f"Existing admin user found: {username} ({admin_id})")
        else:
            print(f"Creating new admin user: {username}")
            cursor.execute("""
                INSERT INTO users (id, username, role, is_active)
                VALUES (?, ?, ?, ?)
            """, (admin_id, username, Role.ADMIN.value, 1))
            conn.commit()
    
    # 3. Create a master API key
    key_name = f"Bootstrap Admin Key ({datetime.utcnow().strftime('%Y-%m-%d %H:%M')})"
    api_key_id, plain_key = manager.create_api_key(user_id=admin_id, name=key_name)
    
    print("\n" + "="*50)
    print("CRITICAL: BOOTSTRAP COMPLETE")
    print("="*50)
    print(f"Admin User: {username}")
    print(f"API Key ID: {api_key_id}")
    print(f"PLAIN-TEXT KEY: {plain_key}")
    print("="*50)
    print("INSTRUCTIONS:")
    print("1. Copy the PLAIN-TEXT KEY above.")
    print("2. Open ALOS.")
    print("3. Paste the key into the login screen.")
    print("")
    print("For packaged macOS builds, prefer the in-app original-admin setup.")
    print("Use this script only for development or explicit recovery work, and set")
    print("ALOS_DATA_DIR if you need to target a packaged app data directory.")
    print("="*50 + "\n")
    
    # Also save to a secure file for reference
    secure_file = str(USER_DATA_DIR / ".admin_bootstrap")
    with open(secure_file, "w") as f:
        f.write(f"ALOS_ADMIN_API_KEY={plain_key}\n")
    print(f"API key also saved to: {secure_file}")
    print("WARNING: This file contains sensitive information!")
    
    return plain_key


if __name__ == "__main__":
    try:
        bootstrap_admin()
    except Exception as e:
        print(f"ERROR during bootstrap: {e}")
        sys.exit(1)
