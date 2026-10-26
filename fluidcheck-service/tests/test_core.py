"""Model logic tests: no web server needed. Run with:  pytest -q"""
import json

import numpy as np
import pytest

from fluidcheck import Recipe, decode_image, diagnose, load_bundle, measure, queue_risk
from fluidcheck.color import expected_absorbance, first_vial_absorbance
from tests.helpers import bundle, make_frames

R6 = Recipe(id="6", t100_ml=30, t200_ml=10)
R7 = Recipe(id="7", t100_ml=20, t400_ml=50)
R12 = Recipe(id="12", t100_ml=10, t200_ml=50, t400_ml=10)


def test_clean_vial_passes():
    b = bundle()
    empty, full = make_frames(expected_absorbance(R7, b), fill_rows=175)
    result = diagnose(measure(empty, full, b), R7, b, prev=R7, batch_position=3)
    assert result.verdict == "pass"
    assert result.delta_e.vs_expected < 1.0
    assert result.causes[0].cause == "none"


def test_first_vial_after_orange_is_flagged_as_carryover():
    """The vial 7 case: blue recipe 7 right after orange recipe 6."""
    b = bundle()
    empty, full = make_frames(first_vial_absorbance(R6, R7, b), fill_rows=175)
    result = diagnose(measure(empty, full, b), R7, b, prev=R6, batch_position=1)
    assert result.verdict in ("watch", "flag")
    assert result.causes[0].cause == "carryover"
    assert result.delta_e.vs_carryover < result.delta_e.vs_expected
    assert "recipe 6" in result.explanation


def test_wrong_recipe_is_named():
    b = bundle()
    empty, full = make_frames(expected_absorbance(R12, b), fill_rows=175)
    result = diagnose(measure(empty, full, b), R7, b, prev=R7, batch_position=3)
    assert result.verdict == "flag"
    assert result.causes[0].cause == "wrong_recipe"
    assert result.delta_e.nearest_other_recipe_id == "12"


def test_volume_estimate_from_fill_height():
    b = bundle()
    empty, full = make_frames(expected_absorbance(R7, b), fill_rows=175)
    m = measure(empty, full, b)
    assert m.volume_ml == pytest.approx(175 * 0.4, abs=1)


def test_response_is_json_serialisable():
    b = bundle()
    empty, full = make_frames(first_vial_absorbance(R6, R7, b), fill_rows=175)
    result = diagnose(measure(empty, full, b), R7, b, prev=R6, batch_position=1, vial_id="v5-007")
    data = json.loads(result.model_dump_json())
    assert data["vial_id"] == "v5-007"
    assert data["measured"]["hex"].startswith("#")
    assert set(data) >= {"verdict", "measured", "expected", "delta_e", "causes", "explanation", "model_version"}


def test_queue_risk_warns_on_colour_change_and_checks_limits():
    b = bundle()
    too_much_orange = Recipe(id="X", t100_ml=10, t200_ml=60)
    resp = queue_risk([R6, R7, R7, too_much_orange], b)
    pairs = [(t.from_recipe_id, t.to_recipe_id) for t in resp.transitions]
    assert pairs == [("6", "7"), ("7", "X")]        # 7 -> 7 is not a change
    assert resp.transitions[0].risk in ("watch", "flag")
    assert any("50 mL" in w for w in resp.recipe_warnings["X"])


def test_bad_inputs_raise_clear_errors():
    b = bundle()
    with pytest.raises(ValueError):
        decode_image(b"not an image")
    small = np.zeros((100, 100, 3), np.uint8)
    with pytest.raises(ValueError, match="outside"):
        measure(small, small, b)


def test_missing_bundle_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_bundle(tmp_path)
