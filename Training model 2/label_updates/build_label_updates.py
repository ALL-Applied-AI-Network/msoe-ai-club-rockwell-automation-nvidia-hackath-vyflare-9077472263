"""Regenerate the Model 4 label-update manifest from recipes.xlsx.

Standard library only. Run from the repository root:
    python "Training model 2/label_updates/build_label_updates.py"
"""
import csv
import hashlib
import json
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKBOOK = ROOT / "Training model 2" / "recipes.xlsx"
CHECKPOINT = ROOT / "backend" / "model4_assets" / "checkpoint.json"
OUT_DIR = Path(__file__).resolve().parent
LABEL_HEADER = "bad or good"
# Model 4 checkpoint vial-key prefixes for each workbook sheet.
SHEETS = {"Recipes_5_to_14": "v5_e", "Recipes_41_50_60_99": "field_v"}
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def col_index(ref):
    letters = "".join(ch for ch in ref if ch.isalpha())
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_sheets(path):
    z = zipfile.ZipFile(path)
    shared = ["".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t"))
              for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS)]
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    sheets = {}
    for s in ET.fromstring(z.read("xl/workbook.xml")).find("m:sheets", NS):
        if s.get("name") not in SHEETS:
            continue
        target = rels[s.get(f"{{{NS['r']}}}id")].lstrip("/").removeprefix("xl/")
        rows = []
        for row in ET.fromstring(z.read("xl/" + target)).iter(f"{{{NS['m']}}}row"):
            values = {}
            for c in row.findall("m:c", NS):
                v = c.find("m:v", NS)
                if v is None:
                    continue
                values[col_index(c.get("r"))] = shared[int(v.text)] if c.get("t") == "s" else v.text
            rows.append((int(row.get("r")), values))
        sheets[s.get("name")] = rows
    return sheets


def as_int(value):
    return int(float(value))


def records(sheet, rows):
    _, header = rows[0]
    cols = {name.strip().lower(): i for i, name in header.items()}
    label_col = cols[LABEL_HEADER]
    # The first row of each sheet has no recorded predecessor.
    out, prev_recipe, batch_preceded_by, position = [], "unknown", "unknown", 0
    for row_number, values in rows[1:]:
        if cols["vial"] not in values:
            continue
        recipe = as_int(values[cols["recipe_id"]])
        if recipe == prev_recipe:
            position += 1
        else:
            position, batch_preceded_by = 1, prev_recipe
        raw = values.get(label_col)
        out.append({
            "sheet": sheet, "row": row_number, "vial_id": as_int(values[cols["vial"]]),
            "recipe_id": recipe, "batch_position": position,
            "previous_vial_recipe_id": prev_recipe, "batch_preceded_by_recipe_id": batch_preceded_by,
            "label_raw": "" if raw is None else raw,
            "label": (raw or "").strip().lower() or "unlabeled",
        })
        prev_recipe = recipe
    return out


def main():
    digest = hashlib.sha256(WORKBOOK.read_bytes()).hexdigest()
    checkpoint = json.loads(CHECKPOINT.read_bytes())
    trained = set(checkpoint["training_vials"])
    policy = checkpoint["source_config"]["first_after_change_policy"]
    workbook_rel = WORKBOOK.relative_to(ROOT).as_posix()

    affected, related = [], []
    for sheet, rows in read_sheets(WORKBOOK).items():
        for r in records(sheet, rows):
            key = f"{SHEETS[sheet]}{r['vial_id']:02d}"
            in_fit = key in trained
            if in_fit:
                previous = "eligible: included in Model 4 training_vials (treated as acceptable recipe example)"
            elif r["batch_position"] == 1:
                previous = f"no visual label: excluded from Model 4 fit as first vial after change ({policy})"
            else:
                previous = "not in Model 4 training_vials"
            row = {
                "model4_vial_key": key, "workbook": workbook_rel, "workbook_sha256": digest,
                "sheet": sheet, "sheet_row": r["row"], "recipe_id": r["recipe_id"], "vial_id": r["vial_id"],
                "batch_position": r["batch_position"], "previous_vial_recipe_id": r["previous_vial_recipe_id"],
                "batch_preceded_by_recipe_id": r["batch_preceded_by_recipe_id"],
                "model4_in_training_fit": in_fit, "previous_label": previous,
                "new_label": r["label"], "new_label_raw": r["label_raw"],
            }
            requested = (sheet == "Recipes_5_to_14" and r["batch_position"] == 1 and r["label"] == "bad") or \
                        (sheet == "Recipes_41_50_60_99" and r["vial_id"] in (17, 22))
            if requested:
                if r["batch_position"] == 1:
                    row["reason"] = (f"Column '{LABEL_HEADER}' = bad. First vial after recipe change; now an explicit "
                                     "human visual bad label, not only a process rule. Already outside the Model 4 fit.")
                else:
                    row["reason"] = (f"Column '{LABEL_HEADER}' = bad on a later vial (batch position "
                                     f"{r['batch_position']}), so it is not explained by first-vial carryover. "
                                     "Model 4 trained on it as an acceptable example.")
                affected.append(row)
            elif r["label"] != "good" and (in_fit or r["batch_position"] == 1):
                if r["label"] == "unlabeled":
                    row["reason"] = ("Blank annotation: visual quality unknown, not good."
                                     + (" Model 4 trained on it." if in_fit else ""))
                else:
                    row["reason"] = f"Column '{LABEL_HEADER}' = bad. First vial after change; already outside the Model 4 fit."
                related.append(row)

    fields = list(affected[0].keys())
    for name, rows in (("model4_affected_vials.csv", affected), ("model4_related_vials.csv", related)):
        with open(OUT_DIR / name, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    print(f"workbook sha256 {digest}; affected {len(affected)}; related {len(related)}")


if __name__ == "__main__":
    main()
