"""Playback timestamps and concise facts from pixel observations, never review labels."""
import hashlib
import math


def completion_time(o):
    times=[e['end'][1] for e in o['source_episode_intervals'] if e.get('end')]
    times+=o.get('sample_actual_seconds') or []
    times+=o.get('departure_interval_seconds') or []
    return max(times,default=0)


def unresolved_outcome(a):
    """Explain the saved decision without changing eligibility or recipe identity."""
    candidates=a['timing'].get('possible_recipe_ids',[])
    title='Unresolved'
    if len(candidates)==1:
        title+=f' — Possible Recipe {candidates[0]}'
    elif candidates:
        title+=' — Multiple Possible Recipes'
    parts=[]
    boundary=a['timing'].get('status')=='BOUNDARY_UNCERTAIN'
    color=a['color']['status']
    if color=='CONSISTENT' and len(candidates)==1:
        parts.append(f"Final color resembles Recipe {candidates[0]}"+(
            ', but dispense timing remains at the matching boundary.' if boundary else '.'))
    else:
        if color=='CONSISTENT':parts.append('Final color resembles the possible recipe patterns.')
        elif color=='CONFLICTING':parts.append('Final color conflicts with the possible recipe pattern; color review is required.')
        elif color=='UNRELIABLE':parts.append('The available color evidence is insufficient for a reliable comparison.')
        else:parts.append('No final-color recipe comparison was available.')
        if boundary:parts.append('Dispense timing remains at the matching boundary.')
    if a['timing'].get('status')=='AMBIGUOUS':
        parts.append('Dispense timing fits more than one recipe pattern.')
    flags=set(a.get('hold_reasons',[]))
    explanations={
        'ARRIVAL_LEFT_CENSORED':'The vial was also present before recording began, so its arrival was not observed.',
        'COLOR_SAMPLING_UNRELIABLE':'The final-color samples did not pass the stability checks.',
        'POSTFILL_SAMPLE_PHASE_NOT_SUPPORTED':'Usable final-color samples after dispensing and before departure were not confirmed.',
        'VISIT_END_NOT_OBSERVED':'The recording did not confirm the end of this vial visit.',
        'FLOW_END_NOT_OBSERVED':'The end of dispensing was not observed.',
        'UNRESOLVED_FLOW_VISIBILITY':'Flow visibility was insufficient to confirm the dispense timing.',
    }
    for flag,explanation in explanations.items():
        if flag in flags:parts.append(explanation)
    remaining=flags-set(explanations)-{'AVAILABLE_DEMO_CHECKS_NOT_PASSED'}
    if remaining or (flags=={'AVAILABLE_DEMO_CHECKS_NOT_PASSED'}):
        parts.append('Other observation checks prevent assigning a recipe.')
    parts.append('No recipe ID was assigned or created.')
    return title,' '.join(parts)


def clarify_saved_outcomes(events, assessments):
    """Update old log wording using immutable decisions, never future memberships."""
    by_label={}
    for a in assessments:
        by_label.setdefault(a['observation']['label'],[]).append(a)
    result=[]
    for e in events:
        matches=by_label.get(e.get('vial'),[])
        if e.get('kind')=='recipe' and e.get('title')=='Unresolved' and len(matches)==1 and matches[0]['action']=='UNRESOLVED':
            title,detail=unresolved_outcome(matches[0])
            if e.get('detail','').startswith('Earlier fill pattern updated after another qualifying observation.'):
                detail='Earlier fill pattern updated after another qualifying observation. '+detail
            e={**e,'title':title,'detail':detail}
        result.append(e)
    return result


def outcome(a):
    membership=a.get('pattern_membership') or {}; flags=list(a['hold_reasons'])
    tracking=a.get('recorded_tracking') or {}
    if tracking.get('status')=='HELD':title='Unresolved · Tracking Evidence Held'
    elif membership.get('status')=='DISCOVERED_UNVERIFIED':title=f"Observed Recipe {membership['recipe_id']} · Unverified · Color Review"
    elif membership.get('status')=='PENDING_REPEAT':title=f"Pending Pattern · {membership['qualifying_fill_count']}/{membership['required_fill_count']} Qualifying Fills"
    elif a['action']=='CREATE_DISCOVERED_PATTERN':title=f"Discovered Recipe {a['recipe_id']} · Unverified"
    elif a['action']=='REUSE_DISCOVERED_PATTERN':title=f"Reused Recipe {a['recipe_id']} · Unverified"
    elif a['action']=='REUSE_REFERENCE_PATTERN':title=f"Reference Pattern {a['recipe_id']} · Identity Unconfirmed"
    else:return unresolved_outcome(a)
    details=[]
    if a['timing']['possible_recipe_ids']:details.append('Timing candidates: '+', '.join(map(str,a['timing']['possible_recipe_ids'])))
    details.append('Color check: '+a['color']['status'].replace('_',' ').lower())
    flags+=membership.get('review_flags',[])
    if flags:details.append('Flags: '+', '.join(sorted(set(flags))).replace('_',' ').lower())
    return title,'. '.join(details)


def event(key,at,kind,label,title,detail):
    if not isinstance(at,(int,float)) or not math.isfinite(at) or at<0:raise ValueError('Invalid log evidence time')
    return {'id':hashlib.sha256(key.encode()).hexdigest()[:24],'at':at,'kind':kind,'vial':label,'title':title,'detail':detail,'provenance':'FRESH_RECORDED_VIDEO_OBSERVATION'}


def observation_events(a, include_outcome=True):
    o=a['observation'];key=o['source_lineage']['video_sha256']+':'+o['observation_id'];label=o['label'];items=[]
    previous=None
    for i,e in enumerate(o['source_episode_intervals'],1):
        items.append(event(key+f':start:{i}',e['start'][1],'flow',label,f'Dispense {i} Observed',f"Start bracket: {e['start'][0]:.2f}–{e['start'][1]:.2f} s. Ingredient identity is unknown."))
        if previous is not None:
            items.append(event(key+f':wait:{i}',e['start'][1],'timing',label,'Pause Between Dispenses',f"No-flow interval: {max(0,e['start'][0]-previous[1]):.2f}–{max(0,e['start'][1]-previous[0]):.2f} s."))
        if e.get('end'):
            lo,hi=o['duration_bounds_seconds'][i-1]
            items.append(event(key+f':end:{i}',e['end'][1],'timing',label,f'Dispense {i} Ended',f'Duration: {lo:.2f}–{hi:.2f} s.'))
            previous=e['end']
    raw=o.get('raw_rgb');times=o.get('sample_actual_seconds') or []
    if raw and times:
        rgb=raw['nominal'];r,g,b=rgb
        # Descriptive pixel appearance, never ingredient or recipe identity.
        if max(rgb)-min(rgb)<20:appearance='Neutral / Low Saturation'
        elif b>r and b>g:appearance='Blue-Dominant'
        elif g>r and g>b:appearance='Green-Dominant'
        else:appearance='Red / Orange-Dominant'
        items.append(event(key+':color',max(times),'color',label,'Post-Flow Appearance Sampled',f"{appearance} · Median RGB {', '.join(str(round(c,1)) for c in rgb)}. Quality flags still apply."))
    if include_outcome:
        title,detail=outcome(a);items.append(event(key+':recipe',completion_time(o),'recipe',label,title,detail))
    return items


def playback_events(snapshots,held_visits=()):
    items=[]
    for snap in snapshots:
        a=snap['assessment'];o=a['observation'];key=o['source_lineage']['video_sha256']+':'+o['observation_id']
        if snap['initial']:items.extend(observation_events(a,False))
        title,detail=outcome(a)
        if not snap['initial']:detail='Earlier fill pattern updated after another qualifying observation. '+detail
        items.append(event(key+':recipe:'+str(snap['sequence']),snap['at'],'recipe',o['label'],title,detail))
    for i,v in enumerate(held_visits):
        at=v.get('available_at')
        if at is not None:items.append(event('held:'+str(i)+':'+v['label'],at,'held',v['label'],'Unresolved · Incomplete Fill Evidence',', '.join(v['hold_reasons']).replace('_',' ').lower()))
    return sorted(items,key=lambda e:(e['at'],e['id']))
