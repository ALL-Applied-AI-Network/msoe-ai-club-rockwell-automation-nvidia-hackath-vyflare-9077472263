"""Experimental interval/RGB comparison of frozen, reviewed observations only.

This engine deliberately has no recipe repository or recipe-creation capability.
It does not invoke Model 2, Model 4, Cosmos, a camera, or a video decoder.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / "recipe_trial_assets"
SCHEMA_VERSION = "reviewed-recipe-trial-response/1"
ENGINE_VERSION = "reviewed-interval-rgb/1"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def validate_shape(value, spec):
    """Validate the restricted JSON Schema keyword subset in our bundled schema."""
    if "const" in spec and (value != spec["const"] or type(value) is not type(spec["const"])):
        raise ValueError("Trial response constant mismatch")
    if "enum" in spec and value not in spec["enum"]:
        raise ValueError("Unknown trial response value")
    types = spec.get("type", [])
    types = [types] if isinstance(types, str) else types
    checks = {"object": isinstance(value, dict), "array": isinstance(value, list),
              "string": isinstance(value, str), "integer": type(value) is int,
              "number": type(value) in (int, float) and math.isfinite(value), "null": value is None}
    if types and not any(checks[t] for t in types):
        raise ValueError("Invalid trial response type")
    if isinstance(value, dict):
        if set(spec.get("required", [])) - set(value):
            raise ValueError("Missing trial response fields")
        if spec.get("additionalProperties") is False and set(value) - set(spec["properties"]):
            raise ValueError("Unexpected trial response fields")
        for key, item in value.items():
            validate_shape(item, spec["properties"][key])
    if isinstance(value, list):
        if not spec.get("minItems", 0) <= len(value) <= spec.get("maxItems", math.inf):
            raise ValueError("Invalid trial response array length")
        for item in value:
            validate_shape(item, spec["items"])
    if type(value) in (int, float):
        if not math.isfinite(value) or not spec.get("minimum", -math.inf) <= value <= spec.get("maximum", math.inf):
            raise ValueError("Invalid trial response number")


def _intervals(bounds):
    if not bounds or any(len(pair) != 2 or any(type(x) not in (int, float) or not math.isfinite(x) for x in pair)
                         or not 0 <= pair[0] <= pair[1] for pair in bounds):
        raise ValueError("Invalid reviewed duration intervals")
    return bounds


def compare_timing(bounds, profiles, allowance):
    _intervals(bounds)
    if type(allowance) not in (int, float) or not math.isfinite(allowance) or allowance < 0:
        raise ValueError("Invalid interval allowance")
    possible, contained = [], []
    for profile in profiles:
        reference = _intervals(profile["duration_bounds_s"])
        if len(reference) != len(bounds):
            continue
        expanded = [(lo - allowance, hi + allowance) for lo, hi in reference]
        if all(qlo <= rhi and qhi >= rlo for (qlo, qhi), (rlo, rhi) in zip(bounds, expanded)):
            possible.append(profile)
        if all(qlo >= rlo and qhi <= rhi for (qlo, qhi), (rlo, rhi) in zip(bounds, expanded)):
            contained.append(profile)
    ids = sorted({p["recipe_id"] for p in possible})
    full = sorted({p["recipe_id"] for p in contained})
    state = ("NO_COMPATIBLE_REFERENCE" if not ids else "AMBIGUOUS" if len(ids) > 1
             else "UNIQUE_TIMING_CANDIDATE" if full else "BOUNDARY_UNCERTAIN")
    reasons = {
        "NO_COMPATIBLE_REFERENCE": "No compatible observed profile; missing catalog references prevent a novelty conclusion.",
        "AMBIGUOUS": "Multiple recipe IDs have compatible chronological episode intervals.",
        "UNIQUE_TIMING_CANDIDATE": "One possible recipe ID and at least one containing actual reference profile; identity remains unconfirmed.",
        "BOUNDARY_UNCERTAIN": "One possible recipe ID, but no single actual expanded reference profile contains all query intervals.",
    }
    return {"status": state, "possible_recipe_ids": ids, "contained_recipe_ids": full,
            "duration_bounds_seconds": deepcopy(bounds), "compatible_reference_profile_ids": sorted(p["vial_uid"] for p in possible),
            "containing_reference_profile_ids": sorted(p["vial_uid"] for p in contained), "reason": reasons[state]}


def compare_color(observation, candidate_ids, profiles, rules):
    sample = observation["raw_rgb"]
    failures = list(observation.get("qualitative_reliability_failures", []))
    comparisons = []
    if sample is None:
        failures.append("NO_VALIDATED_POSTFILL_WINDOW")
    else:
        # Unit fixtures may supply direct measurements. Packaged recorded fills
        # must retain three actual decoded timestamps inside the reviewed window.
        if "reviewed_observation" in observation:
            reviewed = observation["reviewed_observation"]
            frames = observation.get("sampled_frames", [])
            if len(frames) != 3 or not all(reviewed["flowEndUpper"] < f["actual_seconds"] < reviewed["stationaryUntil"] for f in frames):
                failures.append("NO_VALIDATED_POSTFILL_WINDOW")
        if sample["temporal_distance"] > rules["temporal_distance_limit"]:
            failures.append("TEMPORAL_VARIATION_LIMIT_EXCEEDED")
        if sample["region_distance"] > rules["placement_distance_limit"]:
            failures.append("REGION_SENSITIVITY_LIMIT_EXCEEDED")
        for recipe_id in candidate_ids:
            colors = [p["raw_rgb"]["nominal"] for p in profiles if p["recipe_id"] == recipe_id and p.get("raw_rgb")]
            if not colors:
                failures.append("MISSING_REFERENCE_COLOR")
                continue
            distance = min(math.dist(sample["nominal"], color) for color in colors)
            comparisons.append({"recipe_id": recipe_id, "color_distance": distance,
                "experimental_band_result": "CONSISTENT" if distance <= rules["color_distance_limit"] else "CONFLICTING"})
    state = ("UNRELIABLE" if failures else "NOT_EVALUATED" if not candidate_ids else
             "CONFLICTING" if any(c["experimental_band_result"] == "CONFLICTING" for c in comparisons) else "CONSISTENT")
    if state == "NOT_EVALUATED":
        failures.append("NO_TIMING_CANDIDATE_TO_COMPARE")
    return {"status": state, "status_scope": "EXPERIMENTAL_NUMERIC_DIAGNOSTIC",
            "rgb": deepcopy(sample["nominal"]) if sample else None,
            "temporal_distance": sample["temporal_distance"] if sample else None,
            "region_distance": sample["region_distance"] if sample else None,
            "comparisons": comparisons, "reasons": failures, "reliability_independently_validated": False,
            "limitations": ["Offline numerical diagnostic only; capture-domain comparability, registration and settled appearance remain independently unvalidated.",
                            observation["phase_note"]]}


class ReviewedTrialEngine:
    def __init__(self, catalog, catalog_sha, assets=ASSETS):
        assets = Path(assets)
        manifest = json.loads((assets / "manifest.json").read_text())
        if manifest["version"] != 1 or manifest["nominal_catalog_sha256"] != catalog_sha:
            raise ValueError("Trial assets do not match the nominal catalog")
        payloads = {}
        for name in ("reviewed_trial.json", "assessment_response.schema.json"):
            payload = (assets / name).read_bytes()
            if hashlib.sha256(payload).hexdigest() != manifest["sha256"][name]:
                raise ValueError("Trial asset integrity check failed: " + name)
            payloads[name] = json.loads(payload)
        self.bundle = payloads["reviewed_trial.json"]
        self.schema = payloads["assessment_response.schema.json"]
        self.catalog_ids = sorted(map(int, catalog["recipes"]))
        self.catalog_sha = catalog_sha
        self.profiles = self.bundle["profiles"]
        self.rules = self.bundle["rules"]
        if self.bundle["version"] != 1 or self.rules["automatic_recipe_creation"] is not False:
            raise ValueError("Invalid reviewed trial mode")
        if self.rules["relative_timing_allowance"] != 0 or self.rules["color_representation"] != "raw_rgb":
            raise ValueError("Unsupported reviewed trial rules")
        for key in ("timing_allowance_seconds", "color_distance_limit", "temporal_distance_limit", "placement_distance_limit"):
            if type(self.rules[key]) not in (int, float) or not math.isfinite(self.rules[key]) or self.rules[key] < 0:
                raise ValueError("Invalid reviewed trial threshold")
        self.observations = {(o["video_id"], o["vial_id"]): o for o in self.bundle["observations"]}
        if len(self.observations) != len(self.bundle["observations"]):
            raise ValueError("Duplicate reviewed fill identity")
        if (len(self.profiles) != manifest["reference_profile_count"] or len(self.observations) != manifest["observation_count"]
                or len({p["recipe_id"] for p in self.profiles}) != manifest["observed_recipe_count"]
                or any(p["recipe_id"] not in self.catalog_ids for p in self.profiles)):
            raise ValueError("Invalid reviewed trial coverage")

    def coverage(self):
        ids = sorted({p["recipe_id"] for p in self.profiles})
        return {"nominal_recipe_count": len(self.catalog_ids), "observed_recipe_count": len(ids),
                "observed_profile_count": len(self.profiles), "observed_recipe_ids": ids,
                "missing_recipe_ids": sorted(set(self.catalog_ids) - set(ids))}

    def assess(self, video_id, vial_id):
        observation = self.observations[(video_id, vial_id)]
        pulses = observation["reviewed_observation"]["pulses"]
        bounds = []
        for index, p in enumerate(pulses, 1):
            if p["order"] != index or not (p["startLower"] <= p["startUpper"] <= p["endUpper"] and p["startLower"] <= p["endLower"] <= p["endUpper"]):
                raise ValueError("Invalid chronological reviewed episode")
            bounds.append([max(0, p["endLower"] - p["startUpper"]), p["endUpper"] - p["startLower"]])
        timing = compare_timing(bounds, self.profiles, self.rules["timing_allowance_seconds"])
        color = compare_color(observation, timing["possible_recipe_ids"], self.profiles, self.rules)
        provenance = {"timing": digest(observation["reviewed_observation"]),
            "color": digest({"query": observation["raw_rgb"], "reference_colors": [p.get("raw_rgb") for p in self.profiles]}),
            "rules": digest(self.rules), "profiles": digest(self.profiles),
            "measurements": digest(observation), "catalog": self.catalog_sha,
            "diagnostics": digest({"engine_version": ENGINE_VERSION, "schema": self.schema,
                "lineage": self.bundle["source_hashes"], "images": self.bundle["image_hashes"], "limitations": self.bundle["limitations"]})}
        revision = digest({"source": observation["source"], "provenance": provenance, "schema_version": SCHEMA_VERSION})
        result = {"schema_version": SCHEMA_VERSION, "assessment_id": "trial-format:" + revision, "revision": revision,
            "generated_at": datetime.now(timezone.utc).isoformat(), "experimental": True, "source": deepcopy(observation["source"]),
            "timing": timing, "color": color, "review_flags": ["COLOR_CONFLICT_REVIEW"] if color["status"] == "CONFLICTING" else [],
            "coverage": self.coverage(), "provenance": provenance,
            "overall": {"status": "INSUFFICIENT_EVIDENCE", "confirmed_recipe_id": None, "automatic_recipe_creation": False,
                "reasons": ["EXPERIMENTAL_TRIAL", "REFERENCE_COVERAGE_INCOMPLETE", "EVENT_INGREDIENT_COMPLETENESS_UNVERIFIED"]}}
        validate_shape(result, self.schema)
        return result
