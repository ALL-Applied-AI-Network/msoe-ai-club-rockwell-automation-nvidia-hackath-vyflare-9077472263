"""Step 1: vial and media manifests with provenance, eligibility and grouped folds.

Run measure_flow_end.py first; it supplies the no-flow boundary for every vial.
"""
import csv
import json
import re

from PIL import Image

from common import CONFIG, DATA, FIELD_CONCAT, FIELD_RECORDINGS, OUT, TM2, VIDEO5, WORKBOOK, sha256, workbook_vials

WB_SHA = sha256(WORKBOOK)
# Operator-confirmed: photo/clip suffix k is batch position k within the folder's batch.
FIELD_FOLDER_FIRST_VIAL = {"41": 1, "99/41-flush": 6, "60": 11, "99/60-flush": 16, "50": 21, "99/50-flush": 26}


def field_recording_for(start_s):
    """Recording whose concatenated span contains start_s (start frames verified identical)."""
    chosen = None
    for rec in FIELD_RECORDINGS:
        if start_s >= rec[3] - 1e-6:
            chosen = rec
    meta = json.loads((DATA / chosen[0]).read_text())
    return chosen, meta


def vial_rows():
    bounds = {r["vial_key"]: r for r in csv.DictReader(open(OUT / "flow_boundaries.csv", encoding="utf-8"))}
    rows = []
    for v in workbook_vials():
        field = v["sheet"] == "Recipes_41_50_60_99"
        b = bounds[v["vial_key"]]
        row = {
            "vial_key": v["vial_key"], "workbook": WORKBOOK.relative_to(TM2.parent).as_posix(),
            "workbook_sha256": WB_SHA, "sheet": v["sheet"], "sheet_row": v["row"], "vial_id": v["vial_id"],
            "intended_recipe_id": v["recipe_id"], "label_raw": v["label_raw"], "visual_quality_label": v["label"],
            "batch_position": v["batch_position"], "first_vial_flag": v["batch_position"] == 1,
            "previous_vial_recipe_id": v["previous_vial_recipe_id"],
            "batch_preceded_by_recipe_id": v["batch_preceded_by_recipe_id"],
            "workbook_start_s": v["start_s"], "workbook_end_s": v["end_s"],
            "start_s": b["start_s_used"], "end_s": b["end_s_used"], "boundary_source": b["boundary_source"],
            "camera": "station 640x480",
        }
        if field:
            rec, meta = field_recording_for(v["start_s"])
            row.update(recording_id=meta["recording_id"], batch_id=f"{meta['batch_id']}/{meta['recording_id']}",
                       video_source=FIELD_CONCAT.relative_to(TM2).as_posix(),
                       recording_file=rec[0].replace(".json", ".mp4"),
                       timing_provenance="Recipes_41_50_60_99 timestamps on concatenated timeline; segment verified frame-identical to recording file",
                       sidecar_note=meta["samples"][0]["notes"])
            evidence = "workbook row order; recordings ordered by sidecar started_at; flush folder name (operator-confirmed order)"
        else:
            row.update(recording_id="vial_fill_video_5", batch_id=f"vial_fill_video_5/recipe{v['recipe_id']}",
                       video_source=VIDEO5.relative_to(TM2).as_posix(), recording_file=VIDEO5.name,
                       timing_provenance="video5_vial_recipes.csv (operator instruction; Video-5 playback seconds)",
                       sidecar_note="")
            evidence = "workbook row order within one continuous recording"
        row["previous_recipe_evidence"] = "none: first row of sheet" if v["batch_preceded_by_recipe_id"] == "unknown" else evidence
        row["quarantine"] = ""
        row["label_conflict"] = CONFIG["label_conflicts"].get(v["vial_key"], "")
        rows.append(row)

    for row in rows:
        recipe, label = row["intended_recipe_id"], row["visual_quality_label"]
        reasons = []
        if row["label_conflict"]:
            reasons.append("label conflict: " + row["label_conflict"])
        if recipe in CONFIG["unsupported_recipes"]:
            reasons.append(f"recipe {recipe} unsupported")
        if label != "good":
            reasons.append(f"visual label {label}")
        if row["first_vial_flag"]:
            reasons.append("first vial after change (contamination flag)")
        row["train_eligible"] = not reasons
        row["exclusion_reason"] = "; ".join(reasons)
        # Physical-vial folds: fold p holds out batch position p in every batch.
        row["cv_fold"] = row["batch_position"]
        if row["label_conflict"]:
            role = "label_conflict"
        elif label == "unlabeled":
            role = "unknown_quality"
        elif label == "bad":
            role = "C_bad_first" if row["first_vial_flag"] else "C_bad_later"
        else:
            role = "A_good_known"
        row["eval_role"] = role
    return rows


def photo_vial_key(rel):
    """Map data/<folder>/<recipe>-<k>.jpg to a vial key (k = batch position)."""
    folder, name = rel.rsplit("/", 1)
    k = int(re.fullmatch(r"\d+-(\d+)(?:-video)?\.(?:jpg|mp4)", name).group(1))
    if folder in FIELD_FOLDER_FIRST_VIAL:
        return f"field_v{FIELD_FOLDER_FIRST_VIAL[folder] + k - 1:02d}"
    return f"v5_e{3 * (int(folder) - 5) + k:02d}"


def media_rows():
    out = [{"path": WORKBOOK.relative_to(TM2).as_posix(), "sha256": WB_SHA, "kind": "workbook", "camera": "",
            "folder_recipe_id": "", "mapped_vial_keys": "all", "use": "labels and timing",
            "reason": "selected workbook (user decision)"},
           {"path": "video5_vial_recipes.csv", "sha256": sha256(TM2 / "video5_vial_recipes.csv"), "kind": "csv", "camera": "",
            "folder_recipe_id": "5-14", "mapped_vial_keys": "v5_e01..v5_e30", "use": "timing",
            "reason": "operator instruction: start/end times for recipes 5-14"},
           {"path": VIDEO5.relative_to(TM2).as_posix(), "sha256": sha256(VIDEO5), "kind": "video", "camera": "station 640x480",
            "folder_recipe_id": "5-14", "mapped_vial_keys": "v5_e01..v5_e30", "use": "primary frame source",
            "reason": "video5_vial_recipes.csv times are Video 5 playback seconds"}]
    quarantine = set(CONFIG["quarantine_media"])
    for p in sorted(DATA.rglob("*")):
        if not p.is_file() or p.name == ".DS_Store":
            continue
        rel = p.relative_to(DATA).as_posix()
        parts = rel.split("/")
        row = {"path": "data/" + rel, "sha256": sha256(p), "kind": p.suffix.lstrip("."), "camera": "",
               "folder_recipe_id": parts[0] if parts[0] != "99" else f"99 ({parts[1]})", "mapped_vial_keys": "",
               "use": "", "reason": ""}
        if p.suffix == ".jpg":
            img = Image.open(p)
            row["camera"] = f"{img.getexif().get(272) or 'no EXIF'} {img.size[0]}x{img.size[1]}"
            row["mapped_vial_keys"] = photo_vial_key(rel)
        elif p.suffix == ".mp4":
            row["camera"] = "station 640x480"
        if rel in quarantine:
            row.update(use="quarantined", reason="see CONFIG")
        elif rel == FIELD_CONCAT.name:
            row.update(use="primary frame source", mapped_vial_keys="field_v01..field_v30",
                       reason="workbook field timestamps are on this timeline; segments verified frame-identical")
        elif rel == "60/60-video.json":
            row.update(use="recording identity", mapped_vial_keys="field_v11..field_v15",
                       reason="notes 'rec #99' is an operator-confirmed sync error; video verified as recipe 60")
        elif p.suffix in (".mp4", ".json") and parts[0] in ("41", "50", "60", "99"):
            row.update(use="recording identity", reason="frames identical to concatenated segment; sidecar gives recording_id/batch_id")
        elif p.suffix == ".mp4":
            row.update(use="not used", mapped_vial_keys=photo_vial_key(rel),
                       reason="clip cut from Video 5 with video5_vial_recipes.csv window; Video 5 used directly")
        elif "no EXIF" in row["camera"]:
            row.update(use="excluded", reason="station still with unknown capture time (completed fill not established); same vial as its frames")
        else:
            row.update(use="separate phone-camera evaluation", reason="never used for training")
        out.append(row)
    return out


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main():
    vials = vial_rows()
    write_csv(OUT / "vials_manifest.csv", vials)
    write_csv(OUT / "media_manifest.csv", media_rows())
    counts = {}
    for v in vials:
        counts.setdefault(v["eval_role"], []).append(v["vial_key"])
    for k, keys in sorted(counts.items()):
        print(f"{k:18s} {len(keys):3d} {' '.join(keys)}")
    print("train eligible:", sum(v["train_eligible"] for v in vials))


if __name__ == "__main__":
    main()
