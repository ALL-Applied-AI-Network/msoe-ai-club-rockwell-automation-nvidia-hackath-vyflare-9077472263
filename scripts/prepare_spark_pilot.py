"""Prepare an explicitly within-session pilot; never an independent test set."""
import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path

HOLDOUT_RECIPES = {6, 9, 13}
QUESTION = ('Inspect only the vial under the dispensing nozzle, not a neighboring vial. '
            'Describe its visible liquid color sequence across the entire clip. '
            'Return only JSON with observed_color_sequence as an ordered list. '
            'Include observed color changes and shade descriptions.')


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def split_rows(rows, recipes):
    if len(rows) != 30 or {r['source_vial'] for r in rows} != set(range(1, 31)):
        raise ValueError('Pilot requires the original 30 verified vials exactly once')
    if len(recipes) != 30 or len({int(r['vial']) for r in recipes}) != 30:
        raise ValueError('Need 30 unique recipe records')
    recipe_map = {int(r['vial']): int(r['recipe_id']) for r in recipes}
    result = {'train': [], 'val': []}
    for source in rows:
        if source.get('reviewed') is not True:
            raise ValueError('Every target needs human verification')
        target = json.loads(source['answer'])
        colors = target.get('observed_color_sequence')
        if not isinstance(colors, list) or not colors or not all(isinstance(c,str) and c.strip() for c in colors):
            raise ValueError('Invalid color target')
        row = dict(source)
        row.pop('baseline_color', None)
        row['question'] = QUESTION
        row['recipe_id'] = recipe_map[row['source_vial']]
        row['split'] = 'val' if row['recipe_id'] in HOLDOUT_RECIPES else 'train'
        result[row['split']].append(row)
    if {r['recipe_id'] for r in result['train']} & {r['recipe_id'] for r in result['val']}:
        raise ValueError('Recipe-group leakage')
    if {r['sha256'] for r in result['train']} & {r['sha256'] for r in result['val']}:
        raise ValueError('Duplicate media across partitions')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('data/local/video5'))
    parser.add_argument('--recipes', type=Path, default=Path('data/csi-vial-fill-dataset/csi-vial-fill-dataset/vial_fill/labels/video5_vial_recipes.csv'))
    parser.add_argument('--out', type=Path, default=Path('data/local/spark-pilot-v1'))
    args = parser.parse_args()
    if args.out.exists():
        parser.error(f'Refusing to overwrite experiment data: {args.out}')
    manifest = args.source / 'annotations.jsonl'
    rows = [json.loads(line) for line in manifest.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    with args.recipes.open(encoding='utf-8-sig', newline='') as stream:
        partitions = split_rows(rows, list(csv.DictReader(stream)))
    # Check ALL inputs before creating output.
    for row in rows:
        path = (args.source / row['media']).resolve()
        if not path.is_relative_to(args.source.resolve()) or sha256(path) != row['sha256']:
            raise ValueError(f"Media missing, changed, or outside root: {row['id']}")
    (args.out / 'media').mkdir(parents=True)
    for split, records in partitions.items():
        for row in records:
            shutil.copy2(args.source / row['media'], args.out / row['media'])
        (args.out / f'{split}.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
    description = dict(
        dataset_version='spark-pilot-v1', source_model='nvidia/Cosmos3-Nano',
        source_manifest_sha256=sha256(manifest), recipe_manifest_sha256=sha256(args.recipes),
        split_policy='Hold out all vials from recipes 6, 9, 13; all data comes from ONE recording session.',
        evaluation_scope='WITHIN-SESSION DEVELOPMENT ONLY; no independent-session accuracy claim.',
        counts={split:len(records) for split,records in partitions.items()},
        holdout_recipes=sorted(HOLDOUT_RECIPES), t200_source_color='red',
        excluded='Unlinked field photos, unlabeled field video, synthetic mixing, recipe colors, prior model predictions',
    )
    (args.out / 'experiment.json').write_text(json.dumps(description, indent=2), encoding='utf-8')
    print(json.dumps(description, indent=2))


if __name__ == '__main__':
    main()
