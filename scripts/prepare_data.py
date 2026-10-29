"""Stage private media, collect human labels, and build native video SFT JSON.

Python 3.11+. No ML libraries needed for build/validation.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

VIDEO = {".mp4", ".mov", ".avi", ".mkv"}
IMAGE = {".jpg", ".jpeg", ".png", ".webp"}
QUESTION = ("Describe the visible liquid color, clarity, level, and changes over "
            "this clip. State any uncertainty.")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def media_path(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"Missing media or path outside dataset: {relative}")
    return path


def inventory(args):
    import cv2  # Optional media dependency; never imported by build.
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    manifest = root / "annotations.jsonl"
    if manifest.exists():
        raise ValueError(f"Refusing to overwrite labels: {manifest}")
    records = []
    for source in args.media:
        source = source.resolve()
        suffix = source.suffix.lower()
        if suffix not in VIDEO | IMAGE:
            raise ValueError(f"Unsupported media: {source}")
        sha = digest(source)
        relative = f"media/{sha[:16]}{suffix}"
        target = root / relative
        target.parent.mkdir(exist_ok=True)
        shutil.copy2(source, target)
        meta = {}
        if suffix in VIDEO:
            cap = cv2.VideoCapture(str(target))
            try:
                ok, _ = cap.read()
                fps, frames = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                if not ok or fps <= 0 or frames < 1:
                    raise ValueError(f"Cannot decode {source}")
                meta = dict(fps=fps, frames=frames, seconds=frames / fps,
                            width=int(cap.get(3)), height=int(cap.get(4)))
            finally:
                cap.release()
        elif cv2.imread(str(target)) is None:
            raise ValueError(f"Cannot decode {source}")
        records.append(dict(id=source.stem + "-" + sha[:8], media=relative,
                            source_name=source.name, sha256=sha, metadata=meta,
                            group=args.group, split="", usage="train" if suffix in VIDEO else "reference",
                            reviewed=False, question=QUESTION if suffix in VIDEO else
                            "Describe only the visible liquid color, clarity, and level.", answer=""))
    manifest.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    print(f"Staged {len(records)} items. Review and edit {manifest}")


def validate_records(records, root):
    splits = {"train": [], "val": []}
    seen_ids, groups, hashes = set(), {}, {}
    for row in records:
        if row.get("usage") == "reference":
            continue
        if row.get("usage") != "train":
            raise ValueError("Each row needs usage=train or reference")
        identity = row.get("id")
        if not isinstance(identity, str) or not identity.strip() or identity in seen_ids:
            raise ValueError(f"Missing/duplicate id: {identity}")
        seen_ids.add(identity)
        split, group = row.get("split"), row.get("group")
        if split not in splits or not isinstance(group, str) or not group.strip():
            raise ValueError(f"{identity}: assign train/val and recording-session group")
        if row.get("reviewed") is not True:
            raise ValueError(f"{identity}: label requires human review")
        for field in ("question", "answer"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError(f"{identity}: empty {field}")
        path = media_path(root, row["media"])
        if path.suffix.lower() not in VIDEO:
            raise ValueError(f"{identity}: this native recipe accepts videos only; use images as references")
        sha = digest(path)
        if row.get("sha256") and sha != row["sha256"]:
            raise ValueError(f"{identity}: media changed since inventory")
        if group in groups and groups[group] != split:
            raise ValueError(f"Session leakage across splits: {group}")
        if sha in hashes and hashes[sha] != split:
            raise ValueError(f"Identical media across splits: {identity}")
        groups[group], hashes[sha] = split, split
        splits[split].append(dict(id=identity, video=row["media"], conversations=[
            {"from": "human", "value": "<video>\n" + row["question"].strip()},
            {"from": "gpt", "value": row["answer"].strip()}]))
    if not all(splits.values()):
        raise ValueError("Need reviewed videos from independent sessions in BOTH train and val")
    return splits


def build(args):
    root = args.root.resolve()
    manifest = root / "annotations.jsonl"
    records = [json.loads(line) for line in manifest.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    splits = validate_records(records, root)
    for split, rows in splits.items():
        (root / f"{split}.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print({split: len(rows) for split, rows in splits.items()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    stage = sub.add_parser("inventory")
    stage.add_argument("--media", nargs="+", type=Path, required=True)
    stage.add_argument("--group", required=True, help="Recording session; group all related views/clips together")
    stage.add_argument("--root", type=Path, default=Path("data/local"))
    stage.set_defaults(func=inventory)
    make = sub.add_parser("build")
    make.add_argument("--root", type=Path, default=Path("data/local"))
    make.set_defaults(func=build)
    args = parser.parse_args()
    try:
        args.func(args)
    except (ValueError, KeyError, OSError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
