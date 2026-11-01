"""Freeze previously reviewed research; never decode video or invent observations.

Usage: python backend/scripts/package_recipe_trial.py --research-root /path/to/outputs
The research directory is input only. Generated assets run without that directory.
"""
import argparse
import hashlib
import json
from pathlib import Path


def package(research):
    repo = Path(__file__).resolve().parents[2]
    destination = repo / "backend/recipe_trial_assets"
    sources = {
        "reviewed_observations": research / "recipe-footage-review-2026-10-31/revised-recorded-inspection.json",
        "profiles": research / "recipe-footage-review-2026-10-31/comparison/reference_patterns.json",
        "reference_colors": research / "recipe-color-validation-2026-10-31/reference_measurements.json",
        "query_colors": research / "recipe-color-validation-2026-10-31/query_measurements.json",
        "diagnostics": research / "recipe-color-validation-2026-10-31/query_candidate_diagnostics.json",
        "image_hashes": research / "recipe-color-validation-2026-10-31/image_hashes.json",
        "frame_times": research / "recipe-final-color-check-2026-10-31/manifests/frame_extraction.json",
        "rules": research / "recipe-backend-design-2026-10-31/approved_test_rules.json",
        "schema": research / "recipe-backend-design-2026-10-31/assessment_response.schema.json",
        "examples": research / "recipe-backend-design-2026-10-31/validated_response_examples.json",
    }
    raw = {key: path.read_bytes() for key, path in sources.items()}
    data = {key: json.loads(value) for key, value in raw.items()}
    colors = {r["vial_uid"]: r for r in data["reference_colors"]}
    profiles = [{**p, "raw_rgb": colors[p["vial_uid"]]["features"]["raw_rgb"],
                 "recording_id": colors[p["vial_uid"]]["recording_id"]} for p in data["profiles"]]
    measurements = {r["vial"]: r for r in data["query_colors"]}
    notes = {r["vial"]: r for r in data["diagnostics"] if r["representation"] == "raw_rgb"}
    image_hashes = {Path(k).stem: v for k, v in data["image_hashes"].items()}
    observations = []
    for video in data["reviewed_observations"]["videos"]:
        for number, vial in enumerate(video["vials"], 1):
            m = measurements[vial["label"]]
            observations.append({"video_id": video["id"], "vial_id": vial["id"],
                "source": {"label": vial["label"], "video_number": int(video["id"].split("-")[1]), "vial_number": number},
                "reviewed_observation": vial,
                "raw_rgb": m["features"]["raw_rgb"] if m["available"] else None,
                "sampled_frames": [{"id": f["id"], "actual_seconds": f["actual_seconds"], "sha256": image_hashes[f["id"]]}
                                   for f in data["frame_times"] if f["id"].startswith(vial["id"] + "_")],
                "qualitative_reliability_failures": [],
                "phase_note": notes[vial["label"]].get("phase_note", "No validated post-fill sampling window.")})
    bundle = {"version": 1, "rules": data["rules"], "profiles": profiles, "observations": observations,
              "source_hashes": {k: hashlib.sha256(v).hexdigest() for k, v in raw.items()},
              "image_hashes": {str(Path(k).relative_to(research.parent)): v for k, v in data["image_hashes"].items()},
              "limitations": ["Agent visual review, not operator or sensor verification.",
                  "Observed episodes are not verified ingredient or tank dispenses.",
                  "Capture-domain comparability, registration and settled appearance remain independently unvalidated.",
                  "No known qualitative failure is asserted by an empty failure list; numerical color states are experimental."]}
    assert (len(profiles), len(observations), len(bundle["image_hashes"])) == (44, 22, 195)
    assert len({p["recipe_id"] for p in profiles}) == 14
    destination.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(bundle, indent=2, allow_nan=False) + "\n").encode()
    schema = raw["schema"]
    (destination / "reviewed_trial.json").write_bytes(payload)
    (destination / "assessment_response.schema.json").write_bytes(schema)
    catalog = repo / "backend/model4_assets/recipes.json"
    manifest = {"version": 1, "sha256": {"reviewed_trial.json": hashlib.sha256(payload).hexdigest(),
                "assessment_response.schema.json": hashlib.sha256(schema).hexdigest()},
                "nominal_catalog_sha256": hashlib.sha256(catalog.read_bytes()).hexdigest(),
                "reference_profile_count": 44, "observed_recipe_count": 14, "observation_count": 22}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    fixtures = repo / "backend/tests/fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    (fixtures / "recipe_trial_expected.json").write_bytes(raw["examples"])
    print("Packaged 44 profiles, 22 reviewed fills and 195 source image hashes.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", required=True, type=Path)
    package(parser.parse_args().research_root.resolve())
