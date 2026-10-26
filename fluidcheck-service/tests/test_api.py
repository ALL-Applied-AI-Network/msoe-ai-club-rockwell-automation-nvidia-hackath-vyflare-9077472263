"""HTTP tests through FastAPI's TestClient (needs requirements-dev.txt installed)."""
import json
import os

import cv2
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from fluidcheck import Recipe  # noqa: E402
from fluidcheck.color import first_vial_absorbance  # noqa: E402
from tests.helpers import BUNDLE_DIR, bundle, make_frames  # noqa: E402

os.environ["FLUIDCHECK_BUNDLE"] = str(BUNDLE_DIR)
from app.main import app  # noqa: E402

R6 = {"id": "6", "t100_ml": 30, "t200_ml": 10}
R7 = {"id": "7", "t100_ml": 20, "t400_ml": 50}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:  # `with` runs the startup that loads the bundle
        yield c


def png(img):
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_analyze_returns_contract(client):
    b = bundle()
    a = first_vial_absorbance(Recipe(**R6), Recipe(**R7), b)
    empty, full = make_frames(a, fill_rows=175)
    r = client.post(
        "/analyze",
        files={"empty": ("empty.png", png(empty), "image/png"), "full": ("full.png", png(full), "image/png")},
        data={"recipe": json.dumps(R7), "prev_recipe": json.dumps(R6), "batch_position": "1", "vial_id": "v5-007"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["vial_id"] == "v5-007"
    assert body["causes"][0]["cause"] == "carryover"


def test_analyze_rejects_bad_recipe(client):
    empty, full = make_frames([0, 0, 0], fill_rows=10)
    r = client.post(
        "/analyze",
        files={"empty": ("e.png", png(empty), "image/png"), "full": ("f.png", png(full), "image/png")},
        data={"recipe": "{not json"},
    )
    assert r.status_code == 422


def test_queue_risk(client):
    r = client.post("/queue/risk", json={"queue": [R6, R7]})
    assert r.status_code == 200
    assert r.json()["transitions"][0]["to_recipe_id"] == "7"
