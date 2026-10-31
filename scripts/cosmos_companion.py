"""Cosmos-only appearance evidence for Amy's measurement pipeline.

No recipe lookup, tank inference, metrology, tracking or verdict fusion occurs.
Context is caller metadata and is never included in the model prompt.
"""
import copy
import hashlib
import json
import math

SCHEMA='cosmos-vial-observation/1.0'
CONTEXT_FIELDS={'run_id','vial_id','batch_id','camera_id','timebase_id','stage',
                'clip_start_s','binding_verified','event_id'}


def text(value,name):
    if not isinstance(value,str) or not value.strip() or len(value)>128:
        raise ValueError(name+' must be a nonempty string of at most 128 characters')
    return value


def validate_context(value):
    if not isinstance(value,dict):raise ValueError('context must be a JSON object')
    if set(value)-CONTEXT_FIELDS:raise ValueError('Unknown context fields; do not submit expected recipes as observations')
    for name in ('run_id','vial_id','batch_id','camera_id','timebase_id'):
        text(value.get(name),name)
    if value.get('stage') not in {'filling','post_fill','cap_seal'}:raise ValueError('Unsupported caller stage')
    start=value.get('clip_start_s')
    if isinstance(start,bool) or not isinstance(start,(int,float)) or not math.isfinite(start) or start<0:
        raise ValueError('clip_start_s must be a finite nonnegative video-time offset')
    if not isinstance(value.get('binding_verified'),bool):raise ValueError('binding_verified must be an explicit boolean')
    if 'event_id' in value:text(value['event_id'],'event_id')
    return copy.deepcopy(value)


def observation(worker_result,context,input_sha256):
    context=validate_context(context)
    if worker_result.get('media_sha256')!=input_sha256:raise ValueError('Worker input hash does not match uploaded media')
    output=worker_result.get('outputs',{}).get('adapter')
    if not isinstance(output,dict):raise ValueError('Worker did not return the requested adapter result')
    # Validate the worker's parsed object again. Never repair strings into lists.
    parsed=output.get('parsed');colors=parsed.get('observed_color_sequence') if isinstance(parsed,dict) else None
    valid=(isinstance(colors,list) and 0<len(colors)<=64 and all(isinstance(c,str) and c.strip() and len(c)<=128 for c in colors))
    if valid:colors=[c.strip() for c in colors]
    else:colors=None
    kind=worker_result.get('media_kind')
    if kind not in {'video','photo'}:raise ValueError('Unknown worker media kind')
    info=copy.deepcopy(worker_result.get('media_info',{}))
    duration=info.get('duration_seconds') if kind=='video' else None
    if duration is not None:
        if isinstance(duration,bool) or not isinstance(duration,(int,float)) or not math.isfinite(duration) or duration<=0:
            raise ValueError('Invalid worker duration')
    limitations=[
        'Visible liquid appearance only; incoming ingredient identity is not established.',
        'No flow-event boundaries, dispense duration, dose, mixture fractions or calibrated volume were measured.',
        'Caller-supplied vial binding is not model-verified tracking.',
        'No production verdict, recipe match confidence or automatic recipe learning is supplied.'
    ]
    if kind=='video':limitations.append('Only sampled frames are inspected; brief transitions may be missed and color stages have no timestamps.')
    else:limitations.append('Exploratory photo mode; the serving adapter was trained on videos.')
    if context['stage']!='filling':limitations.append('This caller stage is outside the original filling-video training target.')
    if not context['binding_verified']:limitations.append('Vial/media association is unverified; do not attach this result as bound evidence.')
    status='unusable_output' if not valid else 'unbound' if not context['binding_verified'] else 'advisory_only'
    return dict(schema_version=SCHEMA,observation_id=worker_result['run_id'],created_at=worker_result['created_at'],
        producer='cosmos',status=status,context=context,
        appearance=dict(available=bool(valid),observed_color_sequence=colors,
                        final_visible_color=colors[-1] if valid else None,transition_timestamps_s=None),
        evidence_window=dict(timebase_id=context['timebase_id'],start_s=context['clip_start_s'],
                             end_s=context['clip_start_s']+duration if duration is not None else None,
                             annotation_scope='whole_uploaded_clip' if kind=='video' else 'single_image',media_kind=kind),
        provenance=dict(media_sha256=input_sha256,model=copy.deepcopy(worker_result.get('model',{})),
                        worker_request_id=worker_result['run_id'],processing_seconds=worker_result.get('seconds'),
                        prompt_sha256=hashlib.sha256(worker_result.get('prompt','').encode()).hexdigest(),
                        prompt=worker_result.get('prompt'),media_info=info),
        measurements=dict(dispensed_tank=None,flow_events=None,dose_ml=None,mixture_fractions=None,total_volume_ml=None),
        raw_output=output.get('raw_text'),output_schema_valid=bool(valid),limitations=limitations)


def combine_with_model4(cosmos,amy):
    """Attach independent evidence without changing any Amy decision or review."""
    if not isinstance(cosmos,dict) or cosmos.get('schema_version')!=SCHEMA:raise ValueError('Unsupported Cosmos observation contract')
    context=validate_context(cosmos.get('context'))
    if cosmos.get('status')!='advisory_only' or context['binding_verified'] is not True or cosmos.get('output_schema_valid') is not True:
        raise ValueError('Only schema-valid, caller-bound Cosmos evidence can be combined')
    if not isinstance(amy,dict) or not isinstance(amy.get('result'),dict):raise ValueError('Expected the existing Model 4 API response envelope')
    for name in ('vial_id','batch_id'):
        if text(amy.get(name),'Amy '+name)!=context[name]:raise ValueError('Cross-vial or cross-batch evidence mismatch')
    if 'run_id' in amy and amy['run_id']!=context['run_id']:raise ValueError('Run identity mismatch')
    return dict(schema_version='vial-companion-evidence/1.0',vial_id=context['vial_id'],batch_id=context['batch_id'],
                run_id=context['run_id'],amy_response=copy.deepcopy(amy),cosmos_observation=copy.deepcopy(cosmos),
                decision_authority='Amy/backend policy; Cosmos is supporting appearance evidence only',
                combined_verdict=None,recipe_learning_performed=False)
