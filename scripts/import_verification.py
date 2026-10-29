"""Import human-reviewed color sequences without training on baseline model answers.

Read-only workbook access. Outputs ignored local data, with split assignment deferred.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
import openpyxl


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workbook', type=Path, required=True)
    parser.add_argument('--clips', type=Path, required=True)
    parser.add_argument('--out', type=Path, default=Path('data/local/video5'))
    args = parser.parse_args()
    manifest = args.out / 'annotations.jsonl'
    if manifest.exists():
        parser.error(f'Refusing to overwrite {manifest}')
    workbook = openpyxl.load_workbook(args.workbook, read_only=True, data_only=True)
    records = []
    seen = set()
    for index, values in enumerate(workbook['video 5'].iter_rows(values_only=True), 1):
        if not values or not isinstance(values[0], (int, float)):
            continue
        vial = int(values[0])
        if vial != values[0] or not 1 <= vial <= 30 or vial in seen:
            parser.error(f'Invalid or duplicate vial at row {index}')
        seen.add(vial)
        human = values[2]
        if not isinstance(human, str) or not human.strip():
            parser.error(f'Missing human color at C{index}')
        source = args.clips / f'vial-{vial}' / 'clip.mp4'
        if not source.is_file():
            parser.error(f'Missing clip {source}')
        with source.open('rb') as stream:
            sha = hashlib.file_digest(stream, 'sha256').hexdigest()
        records.append(dict(
            id=f'video5-vial-{vial:02d}', media=f'media/vial-{vial:02d}.mp4',
            sha256=sha, group='real-recording-video5', domain='real',
            split='', usage='train', reviewed=True,
            question='Describe the visible liquid color sequence across this entire clip. Return JSON with observed_color_sequence as an ordered list. Include observed color changes and shade descriptions.',
            answer=json.dumps({'observed_color_sequence': [part.strip() for part in human.strip().split(' to ')]}),
            source_workbook=args.workbook.name, source_sheet='video 5', source_cell=f'C{index}',
            source_vial=vial, baseline_color=values[1],
            label_scope='Whole-clip color sequence; transition times and per-frame colors are not labeled.'
        ))
    workbook.close()
    if seen != set(range(1, 31)):
        parser.error('Expected all 30 verified vials')
    (args.out / 'media').mkdir(parents=True, exist_ok=True)
    for row in records:
        shutil.copy2(args.clips / f"vial-{row['source_vial']}" / 'clip.mp4', args.out / row['media'])
    manifest.write_text(''.join(json.dumps(row) + '\n' for row in records), encoding='utf-8')
    print(f'Imported {len(records)} human-reviewed color sequences to {manifest}')
    print('Split is deliberately unassigned: all clips share one source recording.')
    print('Baseline answers are metadata only; prepare_data.py never includes them in model inputs or targets.')


if __name__ == '__main__':
    main()
