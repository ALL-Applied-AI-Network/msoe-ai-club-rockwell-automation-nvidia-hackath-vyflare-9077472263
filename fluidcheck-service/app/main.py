"""FastAPI service: loads the model bundle once and answers the front end.

Run locally:   uvicorn app.main:app --reload
Docs:          http://127.0.0.1:8000/docs
Demo page:     http://127.0.0.1:8000/demo/
"""
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from fluidcheck import (
    QueueRiskRequest,
    QueueRiskResponse,
    Recipe,
    VialResult,
    decode_image,
    diagnose,
    load_bundle,
    measure,
    queue_risk,
)

BUNDLE_DIR = os.environ.get("FLUIDCHECK_BUNDLE", "model_bundle")
CORS_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "FLUIDCHECK_CORS_ORIGINS", "http://localhost:5173,http://localhost:5000,https://localhost:7000"
    ).split(",")
    if o.strip()
]

state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load once at startup, not per request.
    state["bundle"] = load_bundle(BUNDLE_DIR)
    yield
    state.clear()


app = FastAPI(
    title="FluidCheck",
    version="0.1.0",
    description="Vial colour and fill checks with carryover-aware explanations.",
    lifespan=lifespan,
)
# Only needed when a browser front end on another port calls the API directly.
# A C# backend calling server-to-server does not need CORS.
app.add_middleware(
    CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"]
)


def _bundle():
    return state["bundle"]


def _image(upload: UploadFile):
    try:
        return decode_image(upload.file.read())
    except ValueError:
        raise HTTPException(422, f"'{upload.filename}' is not a readable image")


def _recipe(text: Optional[str], field: str) -> Optional[Recipe]:
    if not text:
        return None
    try:
        return Recipe.model_validate_json(text)
    except ValidationError as e:
        raise HTTPException(422, f"{field}: {e.errors()[0]['msg']}")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


@app.get("/health")
def health():
    b = _bundle()
    return {"ok": True, "model_version": b.version, "fitted_on": b.manifest.get("fitted_on")}


# Plain `def` (not async): FastAPI runs it in a worker thread, so slow
# image work does not block other requests.
@app.post("/analyze", response_model=VialResult)
def analyze(
    empty: UploadFile = File(..., description="Frame just before the fill starts"),
    full: UploadFile = File(..., description="Frame just after the fill ends"),
    recipe: str = Form(..., description='JSON, e.g. {"id":"7","t100_ml":20,"t400_ml":50}'),
    prev_recipe: Optional[str] = Form(None, description="JSON recipe that ran before this one"),
    batch_position: Optional[int] = Form(None, description="1, 2 or 3 within the batch"),
    vial_id: Optional[str] = Form(None),
    tank_flags: Optional[str] = Form(None, description='JSON list, e.g. ["tank_did_not_drop:T-400"]'),
):
    b = _bundle()
    r = _recipe(recipe, "recipe")
    prev = _recipe(prev_recipe, "prev_recipe")
    try:
        flags = json.loads(tank_flags) if tank_flags else []
    except json.JSONDecodeError:
        raise HTTPException(422, "tank_flags must be a JSON list of strings")
    try:
        m = measure(_image(empty), _image(full), b)
        return diagnose(m, r, b, prev=prev, batch_position=batch_position, tank_flags=flags, vial_id=vial_id)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post("/queue/risk", response_model=QueueRiskResponse)
def risk(req: QueueRiskRequest):
    try:
        return queue_risk(req.queue, _bundle(), last_run=req.last_run)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post("/recheck", status_code=501)
def recheck():
    """T3 (cap/seal re-check). Needs a cap_seal colour calibration first."""
    raise HTTPException(501, "cap/seal re-check is not implemented yet")


_static = Path(__file__).parent / "static"
app.mount("/demo", StaticFiles(directory=_static, html=True), name="demo")
