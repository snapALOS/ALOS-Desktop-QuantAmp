import sys
import os
from pathlib import Path
from fastapi import FastAPI

# Add backend/src to path
backend_path = Path("/Users/shawnnaprawa/ALOS/ALOS-Desktop/backend")
sys.path.insert(0, str(backend_path))

from src.api.server import discover_and_mount_modules

app = FastAPI()
discover_and_mount_modules(app)

print("\n--- Mounted Routes ---")
for route in app.routes:
    if hasattr(route, "path"):
        print(route.path)

# Check specifically for the hello module
found = any(getattr(route, "path", "") == "/api/hello/hello" for route in app.routes)
if found:
    print("\nSUCCESS: 'hello' module router mounted correctly.")
else:
    print("\nFAILURE: 'hello' module router NOT found.")
    sys.exit(1)
