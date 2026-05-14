from fastapi import APIRouter, Depends, HTTPException
from alos_chamber.chamber_manager import list_active_alos_chambers, run_alos_chamber, stop_alos_chamber
from src.auth.rbac import require_patch_read, require_run_create, require_run_read, require_run_write
from src.runtime.chamber_gate import get_gate, list_chamber_gates, public_chamber_gate_summary

router = APIRouter()

@router.get("/list")
async def get_chambers(_: str = Depends(require_run_read)):
    """List all active sandboxes."""
    return {"chambers": list_active_alos_chambers()}

@router.post("/run")
async def create_chamber(stack: str, command: str | None = None, _: str = Depends(require_run_create)):
    """Launch a new sandbox."""
    result = run_alos_chamber(stack, command)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["output"])
    return result

@router.post("/stop/{container_id}")
async def terminate_chamber(container_id: str, _: str = Depends(require_run_write)):
    """Terminate a sandbox."""
    success = stop_alos_chamber(container_id)
    if not success:
        raise HTTPException(status_code=404, detail="Chamber not found")
    return {"status": "stopped"}


@router.get("/gates")
async def get_gates(status: str | None = None, _: str = Depends(require_patch_read)):
    """List Chamber pre-write build/test gates."""
    return {"gates": list_chamber_gates(status=status)}


@router.get("/gates/summary")
async def get_gate_summary(_: str = Depends(require_patch_read)):
    """Summarize Chamber gate status for dashboards."""
    return public_chamber_gate_summary()


@router.get("/gates/{gate_id}")
async def get_gate_detail(gate_id: str, _: str = Depends(require_patch_read)):
    try:
        return get_gate(gate_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
