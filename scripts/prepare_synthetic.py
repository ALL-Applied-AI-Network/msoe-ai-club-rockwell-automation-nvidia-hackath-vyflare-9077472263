"""Build a source-hashed image/video experiment from the synthetic archive.

Targets describe render controls only. No provisional field targets are used.
Requires Pillow; no GPU or model dependencies.
"""
import argparse
import hashlib
import io
import json
import shutil
import zipfile
from pathlib import Path, PurePosixPath

PALETTE=('amber','blue','cyan','green','lime','magenta','navy','orange','red','teal','violet','yellow')
QUESTION=('Inspect only the liquid in the vial beneath the dispensing nozzle. '
          'Classify its synthetic render-control color using exactly one of: '+', '.join(PALETTE)+'. '
          'This is an appearance-control classification, not chemical or recipe identification. '
          'Return only JSON with render_color_class as one string from that palette.')


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def partition(records):
    """Tail 20% of authored frames held out; two-frame gap and hash purging.

    Fixed scene remains shared. This is development separation, not simulation
    generalization. Same SHA can never enter both partitions.
    """
    frames=sorted({r['frame'] for r in records})
    if len(frames)<10:raise ValueError('Need at least ten distinct authored frames')
    cut=int(len(frames)*.8)
    val_frames=set(frames[cut:]);train_frames=set(frames[:cut-2])
    validation=[];seen=set()
    for r in sorted(records,key=lambda r:(r['frame'],r['synthetic_color_name'])):
        if r['frame'] in val_frames and r['sha256'] not in seen:
            validation.append(r);seen.add(r['sha256'])
    training=[];train_hashes=set()
    for r in sorted(records,key=lambda r:(r['frame'],r['synthetic_color_name'])):
        if r['frame'] in train_frames and r['sha256'] not in seen|train_hashes:
            training.append(r);train_hashes.add(r['sha256'])
    if {r['synthetic_color_name'] for r in training}!=set(PALETTE) or {r['synthetic_color_name'] for r in validation}!=set(PALETTE):
        raise ValueError('Every palette class must be represented in both partitions')
    return training,validation,dict(train_frame_candidates=sorted(train_frames),
        heldout_frames=sorted(val_frames),gap_frames=frames[cut-2:cut],
        excluded_or_deduplicated=len(records)-len(training)-len(validation))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--real-pilot',type=Path,required=True,help='Verified original color pilot for replay/regression')
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    if args.out.exists():p.error('Choose a new output version; overwrite refused')
    from PIL import Image
    with zipfile.ZipFile(args.archive) as archive:
        candidates=[n for n in archive.namelist() if n.endswith('/data output/dataset_manifest.jsonl')]
        if len(candidates)!=1:raise ValueError('Need exactly one dataset manifest')
        manifest=candidates[0];prefix=manifest.rsplit('/',1)[0]+'/'
        records=[json.loads(s) for s in archive.read(manifest).decode('utf-8-sig').splitlines() if s.strip()]
        ids=set();pairs=set()
        for r in records:
            image=PurePosixPath(r['image'])
            if image.is_absolute() or '..' in image.parts or '\\' in r['image']:
                raise ValueError('Unsafe archive member')
            if r['case_id'] in ids:raise ValueError('Duplicate case ID')
            ids.add(r['case_id'])
            pair=(r['frame'],r['synthetic_color_name'])
            if pair in pairs:raise ValueError('Duplicate frame/class case')
            pairs.add(pair)
            if r['synthetic_color_name'] not in PALETTE or r.get('fill_is_measured_volume') is not False:
                raise ValueError('Unsupported render label/measurement scope')
            if r.get('dataset_status')!='synthetic_experiment':raise ValueError('Missing synthetic provenance')
            data=archive.read(prefix+r['image'])
            if hashlib.sha256(data).hexdigest()!=r['sha256']:raise ValueError('Image hash mismatch')
            with Image.open(io.BytesIO(data)) as im:
                im.load()
                if im.size!=(640,480):raise ValueError('Unexpected render dimensions')
        train,val,split=partition(records)
        if len(records)!=600:raise ValueError('Expected the supplied 600-case dataset')
        real={name:json.loads((args.real_pilot/f'{name}.json').read_text()) for name in ('train','val')}
        if {r['recipe_id'] for r in real['train']}&{r['recipe_id'] for r in real['val']}:
            raise ValueError('Real pilot recipe leakage')
        for rows in real.values():
            for r in rows:
                path=(args.real_pilot/r['media']).resolve()
                if r.get('reviewed') is not True or not path.is_relative_to(args.real_pilot.resolve()) or sha(path)!=r['sha256']:
                    raise ValueError('Real replay must use unchanged reviewed original pilot data')
        (args.out/'media').mkdir(parents=True)
        output={}
        for name,selected in [('train',train),('val',val)]:
            result=[]
            for r in selected:
                relative='media/'+r['sha256']+'.png'
                (args.out/relative).write_bytes(archive.read(prefix+r['image']))
                result.append(dict(id=r['case_id'],media=relative,sha256=r['sha256'],
                    modality='image',domain='synthetic',split_group=f"synthetic-frame-{r['frame']}",
                    target_kind='render_control',target_provenance='synthetic_material_control_not_chemical_or_visual_ground_truth',
                    frame=r['frame'],question=QUESTION,answer=json.dumps({'render_color_class':r['synthetic_color_name']})))
            for source in real[name]:
                r=dict(source);relative='media/'+r['sha256']+'.mp4'
                shutil.copy2(args.real_pilot/r['media'],args.out/relative)
                r.update(media=relative,modality='video',target_kind='observed_color',split_group=f"real-video5-recipe-{r['recipe_id']}")
                result.append(r)
            output[name]=result
            (args.out/f'{name}.json').write_text(json.dumps(result,indent=2))
        description=dict(dataset_version=args.out.name,source_model='nvidia/Cosmos3-Nano',
            source_archive_sha256=sha(args.archive),source_manifest_sha256=hashlib.sha256(archive.read(manifest)).hexdigest(),
            real_pilot_experiment_sha256=sha(args.real_pilot/'experiment.json'),
            split_contract='mixed-modality-v1',palette=list(PALETTE),split_details=split,
            counts={k:dict(total=len(v),synthetic=sum(r['domain']=='synthetic' for r in v),real=sum(r['domain']=='real' for r in v)) for k,v in output.items()},
            evaluation_scope='Synthetic frame-block and original same-session real recipe holdouts: DEVELOPMENT ONLY, not field accuracy.',
            limitations=['Synthetic labels are render-control classes, not perceived-color ground truth or chemicals',
                        'Fixed synthetic scene; near-duplicate appearance can persist despite hash dedup and temporal gap',
                        'Original real validation was previously inspected; not a fresh final test',
                        'No provisional field labels, mixing, measured volume, or defect targets'])
        (args.out/'experiment.json').write_text(json.dumps(description,indent=2))
        print(json.dumps(description,indent=2))


if __name__=='__main__':main()
