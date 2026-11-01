"""Paired coarse/refined bank replay from one fresh, source-linked producer run."""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from recipes.demo_api import RecordedDemoService
from recipes.workflow_api import load_reference_catalog
from recipes.reviewed_trial import ReviewedTrialEngine


def coarse_copy(observation):
    o=deepcopy(observation);original=o['timing_refinement']['baseline_episode_intervals']
    intervals=[{'start':e['start_interval_seconds'],'end':e['end_interval_seconds']} for e in original]
    o['source_episode_intervals']=intervals;o['episodes']=deepcopy(intervals)
    o['duration_bounds_seconds']=[[e['end'][0]-e['start'][1],e['end'][1]-e['start'][0]] for e in intervals]
    o['observation_id']='coarse-control:'+o['observation_id']
    o['timing_refinement']={'status':'COARSE_CONTROL','baseline_episode_intervals':original}
    return o


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',type=Path,required=True);args=parser.parse_args()
    folder=args.run;fresh=json.loads((folder/'fresh-results.json').read_text())
    observations=[r['assessment']['observation'] for r in fresh['results']]
    catalog,sha=load_reference_catalog()
    with TemporaryDirectory(prefix='paired-timing-') as tmp:
        coarse=RecordedDemoService(sha,ReviewedTrialEngine(catalog,sha),Path(tmp)/'coarse.sqlite3',[Path(tmp)/'normal.sqlite3'])
        try:
            control=coarse.bank.assess_many([coarse_copy(o) for o in observations])
            pairs=[]
            for old,new in zip(control['results'],fresh['results']):
                a,b=old['assessment'],new['assessment']
                assert a['observation']['raw_rgb']==b['observation']['raw_rgb']
                assert a['observation']['sample_actual_seconds']==b['observation']['sample_actual_seconds']
                assert a['observation']['candidate_appearance_window_seconds']==b['observation']['candidate_appearance_window_seconds']
                pairs.append({'label':b['observation']['label'],'baseline_action':a['action'],'refined_action':b['action'],
                    'baseline_recipe_id':a['recipe_id'],'refined_recipe_id':b['recipe_id'],
                    'baseline_reason':a['reason'],'refined_reason':b['reason'],
                    'refinement_status':b['observation']['timing_refinement']['status'],
                    'refinement_reason':b['observation']['timing_refinement']['reason'],
                    'hold_reasons':b['hold_reasons'],'color_status':b['color']['status']})
            summary={'fills_in_denominator':len(pairs),'baseline_id_links':sum(r['baseline_recipe_id'] is not None for r in pairs),
                'refined_id_links':sum(r['refined_recipe_id'] is not None for r in pairs),
                'baseline_actions':dict(Counter(r['baseline_action'] for r in pairs)),
                'refined_actions':dict(Counter(r['refined_action'] for r in pairs)),
                'refinement_status_counts':dict(Counter(r['refinement_status'] for r in pairs)),
                'fallback_reasons':dict(Counter(r['refinement_reason'] for r in pairs if r['refinement_status']!='REFINED')),
                'postfill_color_inputs_identical':True,'existing_database_opened':False,
                'majority_assignment_goal_met':sum(r['refined_recipe_id'] is not None for r in pairs)>len(pairs)/2}
            (folder/'paired-comparison.json').write_text(json.dumps({'summary':summary,'fills':pairs},indent=2)+'\n')
            print(json.dumps(summary,indent=2))
            for r in pairs:
                if r['baseline_action']!=r['refined_action']:print('CHANGED',r)
        finally:coarse.bank.close()

if __name__=='__main__':main()
