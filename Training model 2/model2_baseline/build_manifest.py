"""Step 1: vial and media manifests with provenance, eligibility and grouped folds."""
import csv
import json

from PIL import Image

from common import CONFIG, DATA, FIELD_CONCAT, FIELD_RECORDINGS, OUT, TM2, VIDEO5, WORKBOOK, sha256, workbook_vials

WB_SHA = sha256(WORKBOOK)


def field_recording_for(start_s):
    """Recording whose concatenated span contains start_s (start frames verified identical)."""
    chosen = None
    for rec in FIELD_RECORDINGS:
        if start_s >= rec[3] - 1e-6:
            chosen = rec
    meta = json.loads((DATA / chosen[0]).read_text())
    return chosen, meta


def vial_rows():
    rows = []
    for v in workbook_vials():
        field = v["sheet"] == "Recipes_41_50_60_99"
        row = {
            "vial_key": v["vial_key"], "workbook": WORKBOOK.relative_to(TM2.parent).as_posix(),
            "workbook_sha256": WB_SHA, "sheet": v["sheet"], "sheet_row": v["row"], "vial_id": v["vial_id"],
            "intended_recipe_id": v["recipe_id"], "label_raw": v["label_raw"], "visual_quality_label": v["label"],
            "batch_position": v["batch_position"], "first_vial_flag": v["batch_position"] == 1,
            "previous_vial_recipe_id": v["previous_vial_recipe_id"],
            "batch_preceded_by_recipe_id": v["batch_preceded_by_recipe_id"],
            "start_s": v["start_s"], "end_s": v["end_s"], "camera": "station 640x480",
        }
        if field:
            rec, meta = field_recording_for(v["start_s"])
            row.update(recording_id=meta["recording_id"], batch_id=f"{meta['batch_id']}/{meta['recording_id']}",
                       video_source=FIELD_CONCAT.relative_to(TM2).as_posix(),
                       recording_file=rec[0].replace(".json", ".mp4"),
                       timing_provenance="Recipes_41_50_60_99 start_s/end_s on concatenated timeline; segment verified frame-identical to recording file",
                       sidecar_note=meta["samples"][0]["notes"])
            evidence = "workbook row order; recordings ordered by sidecar started_at; flush folder name"
            if meta["recording_id"] in CONFIG["quarantine_recordings"]:
                row["quarantine"] = f"recording sidecar notes '{meta['samples'][0]['notes']}' conflict with workbook recipe {v['recipe_id']}"
            if v["vial_id"] in range(16, 21):
                evidence += "; preceding recording (recipe 60 per workbook) has conflicting sidecar"
        else:
            row.update(recording_id="vial_fill_video_5", batch_id=f"vial_fill_video_5/recipe{v['recipe_id']}",
                       video_source=VIDEO5.relative_to(TM2).as_posix(), recording_file=VIDEO5.name,
                       timing_provenance="Recipes_5_to_14 end_s (updated timing, Video-5 playback seconds)",
                       sidecar_note="")
            evidence = "workbook row order within one continuous recording"
        row["previous_recipe_evidence"] = "none: first row of sheet" if v["batch_preceded_by_recipe_id"] == "unknown" else evidence
        row.setdefault("quarantine", "")
        rows.append(row)

    for row in rows:
        recipe, label = row["intended_recipe_id"], row["visual_quality_label"]
        reasons = []
        if row["quarantine"]:
            reasons.append("quarantined: " + row["quarantine"])
        if recipe in CONFIG["unsupported_recipes"]:
            reasons.append(f"recipe {recipe} unsupported: no verified good examples")
        if label != "good":
            reasons.append(f"visual label {label}")
        if row["first_vial_flag"]:
            reasons.append("first vial after change (contamination flag)")
        row["train_eligible"] = not reasons
        row["exclusion_reason"] = "; ".join(reasons)
        # Physical-vial folds: fold p holds out batch position p in every batch.
        row["cv_fold"] = "" if row["quarantine"] else row["batch_position"]
        if row["quarantine"]:
            role = "quarantined"
        elif label == "unlabeled":
            role = "unknown_quality"
        elif label == "bad":
            role = "C_bad_first" if row["first_vial_flag"] else "C_bad_later"
        elif recipe in CONFIG["unsupported_recipes"]:
            role = "unsupported_good"
        else:
            role = "A_good_known"
        row["eval_role"] = role
    return rows


def media_rows():
    out =[{"path": WORKBOOK.relative_to(TM2).as_posix(), "sha256": WB_SHA, "kind": "workbook", "camera": "",
            "folder_recipe_id": "", "mapped_vial_keys": "all", "use": "labels and timing",
            "reason": "selected workbook (user decision)"},
           {"path": VIDEO5.relative_to(TM2).as_posix(), "sha256": sha256(VIDEO5), "kind": "video", "camera": "station 640x480",
            "folder_recipe_id": "5-14", "mapped_vial_keys": "v5_e01..v5_e30", "use": "primary frame source",
            "reason": "Recipes_5_to_14 end_s is in Video-5 playback seconds"}]
    quarantine = set(CONFIG["quarantine_media"])
    for p in sorted(DATA.rglob("*")):
        if not p.is_file() or p.name == ".DS_Store":
            continue
        rel = p.relative_to(DATA).as_posix()
        row = {"path": "data/" + rel, "sha256": sha256(p), "kind": p.suffix.lstrip("."), "camera": "",
               "folder_recipe_id": rel.split("/")[0], "mapped_vial_keys": "", "use": "", "reason": ""}
        if p.suffix == ".jpg":
            img = Image.open(p)
            model = img.getexif().get(272)
            row["camera"] = f"{model or 'no EXIF'} {img.size[0]}x{img.size[1]}"
        elif p.suffix in (".mp4", ".json"):
            row["camera"] = "station 640x480" if p.suffix == ".mp4" else ""
        parts = rel.split("/")
        if parts[0] == "99":
            row["folder_recipe_id"] = f"99 ({parts[1]})"
        if rel in quarantine:
            row.update(use="quarantined", reason="operator-unconfirmed; conflicting metadata (see CONFIG)")
        elif rel == FIELD_CONCAT.name:
            row.update(use="primary frame source", mapped_vial_keys="field_v01..field_v30",
                       reason="workbook field timestamps are on this timeline; segments verified frame-identical")
        elif p.suffix in (".mp4", ".json") and parts[0] in ("41", "50", "60", "99"):
            row.update(use="recording identity", reason="frames identical to concatenated segment; sidecar gives recording_id/batch_id")
        elif p.suffix == ".mp4":
            row.update(use="not used", reason="clip cut with outdated Video_5 Recipe window (frame count matches); Video 5 used directly with updated timing")
        elif p.suffix == ".jpg" and "no EXIF" in row["camera"]:
            row.update(use="excluded", reason="station still with unconfirmed vial mapping; same physical vials as training frames (leak risk)")
        elif p.suffix == ".jpg":
            row.update(use="separate phone-camera evaluation", mapped_vial_keys="unmapped (filename mapping not operator-confirmed)",
                       reason="never used for training; recipe from folder only")
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
