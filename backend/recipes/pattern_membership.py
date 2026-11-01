"""Persistent two-fill observed-pattern memberships; original decisions are immutable."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import math

from .reviewed_trial import compare_timing
from .reference_color import rejection_reasons

def source_key(observation):
    lineage=observation['source_lineage'];arrival=observation.get('timing_refinement',{}).get('arrival_reference')
    if not arrival or type(arrival.get('actual_seconds')) not in (int,float) or not math.isfinite(arrival['actual_seconds']):
        return None
    if not 0<=arrival['actual_seconds']<observation['source_episode_intervals'][0]['start'][0]:return None
    return lineage['video_sha256']+':arrival:'+str(arrival['actual_seconds'])


def quality_reasons(assessment,rules):
    o=assessment['observation'];reasons=list(assessment['hold_reasons'])
    if assessment.get('action')!='UNRESOLVED' or assessment.get('recipe_id') is not None:reasons.append('ALREADY_ID_LINKED_OR_NOT_UNRESOLVED')
    if len(assessment['timing']['possible_recipe_ids'])!=1:reasons.append('TIMING_CANDIDATE_COUNT_NOT_ONE')
    if not o.get('available_demo_checks_pass'):reasons.append('OBSERVATION_CHECKS_NOT_PASSED')
    if assessment['timing']['status']!='UNIQUE_TIMING_CANDIDATE':reasons.append('TIMING_NOT_UNIQUE_AND_CONTAINED')
    if assessment['color']['status']!='CONFLICTING':reasons.append('NOT_A_RELIABLE_COLOR_CONFLICT')
    if rejection_reasons({'raw_rgb':o.get('raw_rgb')},rules):reasons.append('COLOR_SAMPLING_UNRELIABLE')
    if assessment['color'].get('reference_color_qualification',{}).get('missing_qualified_color_recipe_ids'):
        reasons.append('MISSING_QUALIFIED_REFERENCE_COLOR')
    times=o.get('sample_actual_seconds',[]);window=o.get('candidate_appearance_window_seconds');departure=o.get('departure_interval_seconds')
    if not (o.get('reference_cadence_and_window_check') is True and len(times)==3 and window and departure
            and all(o['source_episode_intervals'][-1]['end'][1]<t<departure[0] and window[0]<t<window[1] for t in times)
            and all(a<b and abs((b-a)-.1)<=.034 for a,b in zip(times,times[1:]))):reasons.append('POSTFILL_SAMPLE_PHASE_NOT_SUPPORTED')
    if source_key(o) is None:reasons.append('MISSING_FILL_LINEAGE')
    return sorted(set(reasons))


def compatible(o,founder,rules):
    def profile(value):return {'recipe_id':1,'vial_uid':'internal-comparison-only',
        'duration_bounds_s':value['duration_bounds_seconds']}
    # Symmetric full containment under the same approved one-second allowance;
    # no overlapping-only match, profile averaging, or transitive group drift.
    return (compare_timing(o['duration_bounds_seconds'],[profile(founder)],rules['timing_allowance_seconds'])['status']=='UNIQUE_TIMING_CANDIDATE'
        and compare_timing(founder['duration_bounds_seconds'],[profile(o)],rules['timing_allowance_seconds'])['status']=='UNIQUE_TIMING_CANDIDATE'
        and math.dist(o['raw_rgb']['nominal'],founder['raw_rgb']['nominal'])<=rules['color_distance_limit'])


SCHEMA = (
    "CREATE TABLE IF NOT EXISTS demo_pending_groups (group_id TEXT PRIMARY KEY, signature TEXT NOT NULL, founder TEXT NOT NULL, recipe_id INTEGER UNIQUE REFERENCES demo_patterns(recipe_id))",
    "CREATE TABLE IF NOT EXISTS demo_group_members (source_fill_key TEXT PRIMARY KEY, observation_key TEXT NOT NULL UNIQUE REFERENCES demo_assessments(observation_key), group_id TEXT NOT NULL REFERENCES demo_pending_groups(group_id), features TEXT NOT NULL, label TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS demo_membership_revisions (revision_id INTEGER PRIMARY KEY AUTOINCREMENT, observation_key TEXT NOT NULL REFERENCES demo_assessments(observation_key), group_id TEXT REFERENCES demo_pending_groups(group_id), recipe_id INTEGER REFERENCES demo_patterns(recipe_id), status TEXT NOT NULL, event TEXT NOT NULL, supersedes_revision_id INTEGER REFERENCES demo_membership_revisions(revision_id), created_at TEXT NOT NULL)",
)


def features(o):
    return {key:deepcopy(o[key]) for key in ('duration_bounds_seconds','raw_rgb')}


def revision(bank, key, group, recipe_id, status, event):
    previous=bank.connection.execute('SELECT revision_id FROM demo_membership_revisions WHERE observation_key=? ORDER BY revision_id DESC LIMIT 1',(key,)).fetchone()
    bank.connection.execute('INSERT INTO demo_membership_revisions (observation_key,group_id,recipe_id,status,event,supersedes_revision_id,created_at) VALUES (?,?,?,?,?,?,?)',
        (key,group,recipe_id,status,event,previous[0] if previous else None,datetime.now(timezone.utc).isoformat()))


def confirmed_matches(bank, observation):
    if observation.get('raw_rgb') is None:return [],[]
    matches=[];partial=[]
    for gid, in bank.connection.execute('SELECT group_id FROM demo_pending_groups WHERE recipe_id IS NOT NULL ORDER BY rowid'):
        members=[json.loads(row[0]) for row in bank.connection.execute('SELECT features FROM demo_group_members WHERE group_id=?',(gid,))]
        supports=[compatible(observation,m,bank.rules) for m in members]
        if all(supports):matches.append(gid)
        elif any(supports):partial.append(gid)
    return matches,partial


def apply_membership(bank, assessment):
    # Called inside the assessment's SQLite transaction, after saving its immutable baseline.
    existing_reuse=assessment['reason']=='KNOWN_OBSERVED_PATTERN_REUSE'
    if not existing_reuse and assessment['reason']=='OBSERVED_PATTERN_AMBIGUOUS':
        revision(bank,assessment['observation_key'],None,None,'AMBIGUOUS_PATTERN','MULTIPLE_OBSERVED_PATTERNS_COMPATIBLE');return
    if not existing_reuse and quality_reasons(assessment,bank.rules):return
    o=assessment['observation'];key=assessment['observation_key'];physical=source_key(o)
    alias=bank.connection.execute('SELECT group_id FROM demo_group_members WHERE source_fill_key=?',(physical,)).fetchone()
    if alias:
        revision(bank,key,alias[0],None,'DUPLICATE_FILL_NOT_COUNTED','SOURCE_FILL_ALREADY_SEEN');return
    if existing_reuse:
        matches,partial=confirmed_matches(bank,o)
        if len(matches)!=1 or partial:raise ValueError('Observed pattern changed inside its transaction')
        gid=matches[0]
        recipe_id=bank.connection.execute('SELECT recipe_id FROM demo_pending_groups WHERE group_id=?',(gid,)).fetchone()[0]
        bank.connection.execute('INSERT INTO demo_group_members VALUES (?,?,?,?,?)',(physical,key,gid,bank.encode(features(o)),o['label']))
        revision(bank,key,gid,recipe_id,'DISCOVERED_UNVERIFIED','PATTERN_REUSED')
        bank.connection.execute('INSERT INTO demo_occurrences VALUES (?,?)',(key,recipe_id));return
    signature=bank.encode(assessment['timing']['possible_recipe_ids'])
    rows=bank.connection.execute('SELECT group_id,founder,recipe_id FROM demo_pending_groups WHERE signature=? ORDER BY rowid',(signature,)).fetchall()
    candidates=[];partial=[]
    for gid,founder,recipe_id in rows:
        members=[json.loads(row[0]) for row in bank.connection.execute('SELECT features FROM demo_group_members WHERE group_id=?',(gid,))]
        matches=[compatible(o,m,bank.rules) for m in members]
        if all(matches):candidates.append((gid,founder,recipe_id))
        elif any(matches):partial.append(gid)
    if len(candidates)>1 or partial:
        # No vote or new ID; retain an explicit immutable ambiguous revision.
        revision(bank,key,None,None,'AMBIGUOUS_PATTERN','MULTIPLE_OBSERVED_PATTERNS_COMPATIBLE');return
    if not candidates:
        count=bank.connection.execute('SELECT COUNT(*) FROM demo_pending_groups').fetchone()[0]
        gid=f'pending-conflict-{count+1:03}';founder=bank.encode(features(o));recipe_id=None
        bank.connection.execute('INSERT INTO demo_pending_groups VALUES (?,?,?,NULL)',(gid,signature,founder))
    else:gid,founder,recipe_id=candidates[0]
    bank.connection.execute('INSERT INTO demo_group_members VALUES (?,?,?,?,?)',(physical,key,gid,bank.encode(features(o)),o['label']))
    revision(bank,key,gid,None,'PENDING_REPEAT','FILL_PENDING')
    members=bank.connection.execute('SELECT observation_key FROM demo_group_members WHERE group_id=? ORDER BY rowid',(gid,)).fetchall()
    if recipe_id is None and len(members)==2:
        current=bank.connection.execute('SELECT MAX(recipe_id) FROM demo_patterns').fetchone()[0] or 0
        recipe_id=max(current,max(bank.nominal_ids,default=0))+1
        founding_key=members[0][0]
        founding=json.loads(bank.connection.execute('SELECT result FROM demo_assessments WHERE observation_key=?',(founding_key,)).fetchone()[0])['observation']
        profile={'vial_uid':f'repeat-conflict-founder-{recipe_id}','recipe_id':recipe_id,
            'duration_bounds_s':deepcopy(founding['duration_bounds_seconds']),'raw_rgb':deepcopy(founding['raw_rgb']),
            'source_observation':founding,'scope':bank.scope,'discovery_origin':'REPEATED_COLOR_CONFLICT',
            'review_flags':['COLOR_CONFLICT_REVIEW'],'possible_baseline_recipe_ids':json.loads(signature)}
        bank.connection.execute('INSERT INTO demo_patterns VALUES (?,?,?)',(recipe_id,founding_key,bank.encode(profile)))
        bank.connection.execute('UPDATE demo_pending_groups SET recipe_id=? WHERE group_id=?',(recipe_id,gid))
        for (member_key,) in members:
            revision(bank,member_key,gid,recipe_id,'DISCOVERED_UNVERIFIED','PATTERN_CONFIRMED_BY_TWO_FILLS')
            bank.connection.execute('INSERT INTO demo_occurrences VALUES (?,?)',(member_key,recipe_id))
    elif recipe_id is not None:
        revision(bank,key,gid,recipe_id,'DISCOVERED_UNVERIFIED','PATTERN_REUSED')
        bank.connection.execute('INSERT INTO demo_occurrences VALUES (?,?)',(key,recipe_id))


def history(bank,key):
    rows=bank.connection.execute('SELECT revision_id,group_id,recipe_id,status,event,supersedes_revision_id,created_at FROM demo_membership_revisions WHERE observation_key=? ORDER BY revision_id',(key,)).fetchall()
    return [dict(zip(('revision_id','group_id','recipe_id','status','event','supersedes_revision_id','created_at'),row),
                 review_flags=['COLOR_CONFLICT_REVIEW']) for row in rows]


def project(bank,assessment):
    result=deepcopy(assessment);revisions=history(bank,assessment['observation_key'])
    if revisions:
        latest=revisions[-1];count=bank.connection.execute('SELECT COUNT(*) FROM demo_group_members WHERE group_id=?',(latest['group_id'],)).fetchone()[0] if latest['group_id'] else 0
        result['pattern_membership']={**latest,'qualifying_fill_count':count,'required_fill_count':2,
            'baseline_timing_candidate_ids':deepcopy(assessment['timing']['possible_recipe_ids']),
            'confirmed_nominal_recipe_id':None,'history':revisions}
    return result


def groups(bank):
    rows=bank.connection.execute('SELECT group_id,signature,founder,recipe_id FROM demo_pending_groups ORDER BY rowid').fetchall()
    result=[]
    for gid,signature,founder,recipe_id in rows:
        members=bank.connection.execute('SELECT observation_key,label FROM demo_group_members WHERE group_id=? ORDER BY rowid',(gid,)).fetchall()
        result.append({'group_id':gid,'label':f'Pending Pattern {int(gid.rsplit("-",1)[-1])}' if recipe_id is None else f'Observed Recipe {recipe_id}','recipe_id':recipe_id,'status':'DISCOVERED_UNVERIFIED' if recipe_id else 'PENDING_REPEAT',
            'required_fill_count':2,'qualifying_fill_count':len(members),'founder':json.loads(founder),
            'baseline_timing_candidate_ids':json.loads(signature),'review_flags':['COLOR_CONFLICT_REVIEW'],
            'members':[{'observation_key':key,'label':label} for key,label in members],
            'confirmed_nominal_recipe_id':None})
    return result
