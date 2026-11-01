"""Fresh source-video smoke test. Only a temporary isolated bank is written."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from recipes.recorded_producer import produce_video
from recipes.demo_api import RecordedDemoService
from recipes.workflow_api import load_reference_catalog
from recipes.reviewed_trial import ReviewedTrialEngine


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    repo=Path(__file__).resolve().parents[2]
    catalog,sha=load_reference_catalog()
    with TemporaryDirectory() as tmp:
        service=RecordedDemoService(sha,ReviewedTrialEngine(catalog,sha),str(Path(tmp)/'fresh.sqlite3'),[Path(tmp)/'normal.sqlite3'])
        try:
            allresults=[]
            for n in (1,2):
                previous={}
                def update(**kw):
                    if kw.get('stage')!=previous.get('stage') or kw.get('progress',0)//10!=previous.get('progress',0)//10: print(n,kw,flush=True)
                    previous.update(kw)
                result=produce_video(repo/f'cosmos-original-dataset/videos/vial_fill_video_{n}.mp4',f'video-{n}',update)
                (out/f'video-{n}-observations.json').write_text(json.dumps(result,indent=2)+'\n')
                saved=service.bank.assess_many(result['observations']);allresults.extend(saved['results'])
                print('FRESH',n,result['event_frame_count'],result['detected_fill_count'],Counter(r['assessment']['action'] for r in saved['results']),flush=True)
                repeat=service.bank.assess_many(result['observations'])
                assert repeat['new_patterns']==0 and repeat['new_assessments']==0
            current={r['observation_key']:r for r in service.bank.assessments()}
            allresults=[{**r,'assessment':current[r['assessment']['observation_key']]} for r in allresults]
            summary={'pattern_groups':service.bank.pending_patterns(),'results':allresults,'counts':service.bank.counts(),'patterns':service.bank.patterns(),
                'action_counts':dict(Counter(r['assessment']['action'] for r in allresults)),
                'fresh_video_decoding':True,'normal_bank_opened':False,'replay_created_duplicates':False}
            (out/'fresh-results.json').write_text(json.dumps(summary,indent=2)+'\n')
            print(summary['counts'],flush=True)
        finally: service.bank.close()

if __name__=='__main__':main()
