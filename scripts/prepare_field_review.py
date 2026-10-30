"""Audit field recipes without promoting provisional observations to SFT labels.

Requires openpyxl for read-only workbook access. Private outputs are review
records, NOT trainer inputs. Source workbook and archive are never modified.
"""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def audit_row(values):
    vial, recipe, _, water, red, blue, total, expected, _, _, start, end, _, tw, tr, tb, observed, notes = values
    amounts = dict(T100=water, T200=red, T400=blue)
    durations = dict(T100=tw, T200=tr, T400=tb)
    flags = ['observations_unverified', 'delivered_volumes_not_measured', 'video_link_unverified']
    if expected != observed:
        flags.append('expected_observed_order_conflict')
    if sum(v or 0 for v in amounts.values()) != total:
        flags.append('recipe_total_conflict')
    span = end-start
    if span <= 0:
        flags.append('invalid_vial_window')
    if any(v is not None and v > span for v in durations.values()):
        flags.append('pour_duration_exceeds_vial_window')
    if sum(v or 0 for v in durations.values()) > span:
        flags.append('summed_pour_duration_exceeds_window')
    if any((amounts[t] or 0)>0 and durations[t] is None for t in amounts):
        flags.append('required_ingredient_duration_missing')
    return dict(id=f'field-vial-{int(vial):02d}', recipe_id=int(recipe),
                session_group='field-2026-10-28-batch-2026-10-0004',
                expected=dict(amounts_ml=amounts, total_ml=total, dispense_order=expected,
                              evidence='recipe_definition_not_measured_delivery'),
                provisional=dict(timeline_start_s=start,timeline_end_s=end,
                                 window_seconds=span,ingredient_duration_s=durations,
                                 visible_dispense_order=observed,notes=notes),
                reviewed=False, answer='', split='unassigned', training_eligible=False,
                flags=flags)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workbook',type=Path,required=True)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.out.exists():
        parser.error('Output already exists; choose a new dataset version')
    import openpyxl
    book=openpyxl.load_workbook(args.workbook,data_only=False,read_only=True)
    sheet=book['Recipes_41_50_60_99']
    rows=[audit_row(list(values)) for values in sheet.iter_rows(min_row=2,max_row=31,max_col=18,values_only=True)]
    bank={int(r[0]):dict(order=r[1],amounts_ml=dict(T100=r[2],T200=r[3],T400=r[4]),total_ml=r[5])
          for r in book['Recipe_Bank'].iter_rows(min_row=2,values_only=True) if isinstance(r[0],(int,float))}
    videos=[]
    with zipfile.ZipFile(args.archive) as archive:
        for name in archive.namelist():
            if not name.startswith('field-data/') or not name.endswith('.json'):
                continue
            metadata=json.loads(archive.read(name))
            media=name[:-5]+'.mp4'
            info=archive.getinfo(media)
            videos.append(dict(archive_member=media,bytes=info.file_size,
                               recording_id=metadata['recording_id'],started_at=metadata['started_at'],
                               duration_s=metadata['duration_s'],samples=metadata['samples']))
        photo_count=sum(n.startswith('field-data/') and n.lower().endswith('.jpg') for n in archive.namelist())
    videos.sort(key=lambda v:v['started_at'])
    # Hypothesis only: sheet has a concatenated timeline; files are separate.
    # Wall-clock recording durations introduce boundary uncertainty; review must
    # establish the true timeline origin before any cutting or training.
    cumulative=0
    boundaries=[]
    for video in videos:
        boundaries.append((cumulative,cumulative+video['duration_s'],video))
        cumulative+=video['duration_s']
    for row in rows:
        p=row['provisional']; matches=[(a,b,v) for a,b,v in boundaries
            if p['timeline_start_s']>=a and p['timeline_end_s']<=b]
        row['source']=dict(sheet='Recipes_41_50_60_99',excel_row=int(row['id'][-2:])+1)
        if len(matches)==1:
            a,b,v=matches[0]
            row['candidate_video_link']=dict(archive_member=v['archive_member'],
                local_start_s=round(p['timeline_start_s']-a,6),
                local_end_s=round(p['timeline_end_s']-a,6),confirmed=False,
                method='Unverified concatenation of recording duration_s in chronological order')
        else:
            row['flags'].append('no_unique_candidate_video_window')
        recipe=bank[row['recipe_id']]
        if recipe['order']!=row['expected']['dispense_order'] or recipe['amounts_ml']!=row['expected']['amounts_ml']:
            row['flags'].append('recipe_bank_disagreement')
    from collections import Counter
    report=dict(dataset_version=args.out.name,source_workbook_sha256=digest(args.workbook),
        source_archive_sha256=digest(args.archive),counts=dict(vials=len(rows),videos=len(videos),photos=photo_count,
        eligible_training_rows=0,eligible_test_rows=0),
        recipe_counts=dict(Counter(r['recipe_id'] for r in rows)),
        flag_counts=dict(Counter(f for row in rows for f in row['flags'])),
        split_policy='Keep all connected field records in one session group. No random 24/6 split.',
        training_status='NOT_STARTED_UNVERIFIED_LABELS',
        required_before_training=['Confirm per-vial video links and timing origins',
        'Verify observed ingredient/source identity and pour boundaries',
        'Keep commanded amounts separate from measured delivery; obtain calibration for volume targets',
        'Provide independent session groups and verified evaluation labels'],
        prior_adapter_policy='Preserve current deployed adapter; no automatic replacement',
        candidate_links_are_not_ground_truth=True)
    args.out.mkdir(parents=True)
    (args.out/'review.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
    (args.out/'recipe-bank.json').write_text(json.dumps(bank,indent=2),encoding='utf-8')
    (args.out/'recordings.json').write_text(json.dumps(videos,indent=2),encoding='utf-8')
    (args.out/'audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
