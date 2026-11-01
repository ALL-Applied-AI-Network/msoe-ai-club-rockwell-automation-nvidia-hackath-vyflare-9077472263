"""Package saved automatic observations; never run inference or populate a bank."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path


def sha(raw):return hashlib.sha256(raw).hexdigest()


def package(research):
    root=Path(__file__).resolve().parents[2]
    inputs={"preflight":research/"recipe-recognition-integration-2026-11-01/preflight.json",
        "offline_results":research/"recipe-recognition-integration-2026-11-01/demo_results.json",
        "observer_predictions":research/"automatic-observer-trace-experiment-2026-11-01/predictions.json",
        "automatic_color":research/"automatic-observer-trace-experiment-2026-11-01/color-refinement/measurements.json"}
    raw={name:path.read_bytes() for name,path in inputs.items()}
    data={name:json.loads(value) for name,value in raw.items()}
    preflight=data["preflight"]
    assert preflight["input_hashes"]["predictions"]==sha(raw["observer_predictions"])
    assert preflight["input_hashes"]["color"]==sha(raw["automatic_color"])
    references=(root/"backend/recipe_trial_assets/reviewed_trial.json").read_bytes()
    catalog=(root/"backend/model4_assets/recipes.json").read_bytes()
    assert preflight["input_hashes"]["profiles"]==sha(references)
    assert preflight["input_hashes"]["catalog"]==sha(catalog)
    observations=[];numbers={1:0,2:0};routes={}
    for source in preflight["observations"]:
        o=deepcopy(source);video=o["video"];numbers[video]+=1
        o["video_id"]=f"video-{video}";o["vial_id"]=f"V{video}-V{numbers[video]:02}"
        o["label"]=f"Video {video} · Vial {numbers[video]}"
        o["source_kind"]="PACKAGED_AUTOMATIC_OBSERVER_SNAPSHOT"
        for frame,seconds in zip(o["source_lineage"]["frame_provenance"],o["sample_actual_seconds"]):
            frame["evidence_id"]=Path(frame.pop("path")).stem
            frame["actual_seconds"]=seconds
        assert o["operational_eligibility"]=="NOT_VALIDATED"
        observations.append(o);routes[o["observation_id"]]=(o["video_id"],o["vial_id"])
    assert numbers=={1:19,2:3}
    bundle={"version":1,"input_mode":"PACKAGED_AUTOMATIC_OBSERVER_SNAPSHOTS","operational_qualification_claim":False,
        "observations":observations,"upstream_sha256":{k:sha(v) for k,v in raw.items()},
        "reference_bundle_sha256":sha(references),"nominal_catalog_sha256":sha(catalog),
        "route_identity_basis":"Filled visits in each video, not barcodes or batch positions",
        "limitations":["Saved automatic-observer output; this API does not decode or inspect a new video.",
            "Available development checks only; original NOT_VALIDATED markers remain.",
            "Discovered patterns are unverified observations, not confirmed chemical compositions.",
            "Boundary cases and color conflicts remain unresolved under the agreed rules."]}
    payload=(json.dumps(bundle,indent=2,allow_nan=False)+"\n").encode()
    assert str(research.resolve()).encode() not in payload and b"/Users/" not in payload
    target=root/"backend/recipe_demo_assets";target.mkdir(exist_ok=True)
    (target/"recorded_observations.json").write_bytes(payload)
    manifest={"version":1,"sha256":{"recorded_observations.json":sha(payload)},"nominal_catalog_sha256":sha(catalog),
        "reference_bundle_sha256":sha(references),"observation_count":22,"video_counts":{"video-1":19,"video-2":3}}
    (target/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    expected=[]
    for wrapper in data["offline_results"]["results"]:
        r=wrapper["assessment"];video,vial=routes[r["observation_id"]]
        expected.append({"video_id":video,"vial_id":vial,**{k:r[k] for k in
            ("observation_id","action","reason","recipe_id","recipe_status","confirmed_nominal_recipe_id","hold_reasons")}})
    (root/"backend/tests/fixtures/recipe_demo_expected.json").write_text(json.dumps(expected,indent=2)+"\n")
    print("Packaged 22 automatic observation snapshots and offline decision oracle; no bank was opened.")


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--research-root",type=Path,required=True)
    package(parser.parse_args().research_root.resolve())
