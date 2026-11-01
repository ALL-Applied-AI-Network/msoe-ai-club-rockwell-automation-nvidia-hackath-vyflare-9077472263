"""Synthetic geometry reports for policy/HTTP tests, never production inference."""
from copy import deepcopy
import math
from recipes.recorded_eligibility import build_report


def with_tracking(observation,identity=None):
    o=deepcopy(observation);o['source_kind']='FRESH_RECORDED_VIDEO_OBSERVATION'
    box={'x':.43,'y':.14,'width':.11,'height':.74}
    lower=max(0,o['source_episode_intervals'][0]['start'][0]-.5);upper=o['departure_interval_seconds'][0]
    identity=identity or 'test-'+o['vial_id'];frames=[]
    for i in range(math.ceil((upper-lower)/.25)):
        frames.append({'captured_at':lower+i*.25,'frame_id':f'synthetic-{i}','sha256':'a'*64,
            'detections':[{'position':'Filling Position','track_id':identity,'status':'TRACKING','box':box}],
            'issues':[],'identity_events':[]})
    checks=[{'actual_seconds':t,'sha256':p['sha256'],'frame_id':p['evidence_id'],'box':box,'dimensions':[640,480]}
        for t,p in zip(o['sample_actual_seconds'],o['source_lineage']['frame_provenance'])]
    o['recorded_geometry']=build_report(o,frames,checks,o['source_lineage']['video_sha256'])
    return o
