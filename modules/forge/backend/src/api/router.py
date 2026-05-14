from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
def health():
    return {"ok": True, "service": "forge"}

@router.get("/status")
def status():
    return {"status": "ready", "capabilities": ["file_ops", "terminal"]}
