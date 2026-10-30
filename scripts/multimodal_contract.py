"""Dependency-free data and metric contracts for mixed image/video LoRA runs."""
import hashlib
import json
from pathlib import Path


def validate_partition(train,val,root,mixed=False):
    if not train or not val:raise ValueError('Both partitions must be nonempty')
    if mixed:
        key='split_group'
        if any(not r.get(key) for r in train+val):raise ValueError('Missing split group')
    else:key='recipe_id'
    if {r[key] for r in train}&{r[key] for r in val}:raise ValueError('Partition-group overlap')
    if {r['sha256'] for r in train}&{r['sha256'] for r in val}:raise ValueError('Duplicate media across partitions')
    if len({r['id'] for r in train+val})!=len(train+val):raise ValueError('Duplicate record ID')
    for r in train+val:
        path=(root/r['media']).resolve()
        if not path.is_relative_to(root.resolve()):raise ValueError('Media path escapes dataset')
        with path.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
        if actual!=r['sha256']:raise ValueError('Changed media: '+r['id'])
        target=json.loads(r['answer'])
        if r.get('target_kind')=='render_control':
            if r.get('domain')!='synthetic' or r.get('modality')!='image' or not isinstance(target.get('render_color_class'),str):
                raise ValueError('Render-control labels require synthetic images')
        elif r.get('reviewed') is not True:raise ValueError('Observed targets require human review')


def eval_subset(rows,limit):
    """Balanced diagnostic subset: all real regression rows, palette coverage."""
    if limit<=0:return rows
    kinds=sorted({r.get('target_kind','observed_color') for r in rows})
    if len(kinds)==1:return rows[:limit]
    real=[r for r in rows if r.get('target_kind')!='render_control']
    if limit<len(real):raise ValueError('Evaluation limit would omit real regression cases')
    return real+[r for r in rows if r.get('target_kind')=='render_control'][:limit-len(real)]


def parse_json(text):
    text=text.strip()
    if text.startswith('```'):text=text.split('\n',1)[1].rsplit('```',1)[0].strip()
    return json.loads(text)


def mixed_metrics(predictions):
    groups={}
    for kind in sorted({r.get('target_kind','observed_color') for r in predictions}):
        rows=[r for r in predictions if r.get('target_kind','observed_color')==kind]
        if kind=='observed_color':
            from train_spark_lora import score_predictions
            groups[kind]=score_predictions(rows)
        else:
            valid=correct=0
            for r in rows:
                expected=json.loads(r['target'])['render_color_class']
                try:
                    value=parse_json(r['prediction'])['render_color_class']
                    if not isinstance(value,str) or not value.strip():raise ValueError('Invalid class')
                    valid+=1;correct+=value.strip().casefold()==expected.casefold()
                except (ValueError,KeyError,TypeError):pass
            groups[kind]=dict(n=len(rows),valid_json=valid,render_control_exact=correct,
                              render_control_exact_rate=correct/len(rows) if rows else None)
    return dict(n=len(predictions),by_target_kind=groups)


class TrainingOrder:
    def __init__(self,rows,rng,balance=False):
        self.rng=rng;self.turn=0
        keys=sorted({r.get('modality','video') for r in rows}) if balance else ['all']
        self.pools={k:[i for i,r in enumerate(rows) if k=='all' or r.get('modality','video')==k] for k in keys}
        self.cursor={k:0 for k in keys};self.keys=keys
        for pool in self.pools.values():rng.shuffle(pool)

    def next(self):
        key=self.keys[self.turn%len(self.keys)];self.turn+=1
        if self.cursor[key]==len(self.pools[key]):
            self.rng.shuffle(self.pools[key]);self.cursor[key]=0
        result=self.pools[key][self.cursor[key]];self.cursor[key]+=1
        return result
