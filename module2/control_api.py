"""
ThirdPartyChaos -- Module 2: Control API
Exposes REST endpoints to activate / clear / query faults.
Run with: uvicorn module2.control_api:app --port 9000
  OR (from module2/): uvicorn control_api:app --port 9000
"""
import sys
from pathlib import Path

# Ensure failure_injector can be found without running in package mode
HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "module1"))

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

# Import the shared state functions (file/Redis backed — no mitmproxy needed)
from failure_injector import set_fault, clear_fault, get_status, VALID_FAULTS

app = FastAPI(title="ThirdPartyChaos Control API", version="1.0")


@app.post("/chaos/set/{fault_name}")
def activate_fault(fault_name: str):
    if not set_fault(fault_name):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown fault '{fault_name}'. Valid: {VALID_FAULTS}",
        )
    return {"ok": True, "active_fault": fault_name}


@app.post("/chaos/clear")
def deactivate_fault():
    clear_fault()
    return {"ok": True, "active_fault": None}


@app.get("/chaos/status")
def fault_status():
    return JSONResponse(get_status())


@app.get("/chaos/faults")
def list_faults():
    return {"valid_faults": VALID_FAULTS}
