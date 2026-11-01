"""Fresh, bounded native video acquisition -> frozen observer -> isolated bank.

No reviewed labels, saved predictions, browser measurements or supplied paths
are accepted. Acquisition is currently qualified for the local macOS decoder.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import itertools
import json
from pathlib import Path
import platform
import shutil
import subprocess
from tempfile import TemporaryDirectory
from threading import RLock

import numpy as np
from PIL import Image

from .demo_store import digest, validate_observation
from .observation.features import extract
from .observation.trace import Config, Observer
from .observation.refine import refine_visits

HERE = Path(__file__).with_name('observation')
CONFIG = json.loads((HERE/'config.json').read_text())
PRODUCER_VERSION = 'fixed-station-native/2'
OFFSETS = [(0,0),(2,0),(-2,0),(0,2),(0,-2),(4,0),(-4,0),(0,4),(0,-4)]


def file_sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024*1024), b''): value.update(chunk)
    return value.hexdigest()


def measure_triplet(paths):
    values=[]; provenance=[]
    for path in paths:
        with Image.open(path) as image:
            if image.format!='PNG' or image.size!=(640,480): raise ValueError('Invalid lossless color sample')
            pixels=np.asarray(image.convert('RGB'), dtype=float)
        values.append([np.median(pixels[370+dy:394+dy,299+dx:325+dx].reshape(-1,3),axis=0) for dx,dy in OFFSETS])
        provenance.append({'evidence_id':path.stem,'sha256':file_sha(path)})
    values=np.asarray(values); aggregate=np.median(values,axis=0)
    return {'nominal':aggregate[0].tolist(),
        'temporal_distance':max(float(np.linalg.norm(values[i,0]-values[j,0])) for i,j in itertools.combinations(range(3),2)),
        'region_distance':float(np.max(np.linalg.norm(aggregate-aggregate[0],axis=1)))}, provenance


class NativeDecoder:
    @staticmethod
    def capability():
        ready=platform.system()=='Darwin' and shutil.which('swiftc') is not None
        return {'available':ready,'decoder':'macOS AVFoundation',
            'reason':None if ready else 'Fresh processing currently requires macOS and the Swift compiler; this deployment has no supported decoder.'}

    def __init__(self, root):
        if not self.capability()['available']: raise ValueError(self.capability()['reason'])
        self.binary=root/'decode'
        subprocess.run(['swiftc','-module-cache-path',str(root/'modules'),str(HERE/'decode.swift'),'-o',str(self.binary)],
            check=True,timeout=120,capture_output=True)

    def decode(self, mode, source, folder, tasks=None):
        folder.mkdir()
        if tasks is not None: (folder/'tasks.json').write_text(json.dumps(tasks,allow_nan=False))
        subprocess.run([str(self.binary),mode,str(source),str(folder)],check=True,timeout=240,capture_output=True)
        records=json.loads((folder/'manifest.json').read_text())
        if not records or len(records)>(9600 if mode=='windows' else 7200) or any(r['width']!=640 or r['height']!=480 for r in records):
            raise ValueError('Invalid decoded frame coverage')
        return records


def produce_video(source, video_id, progress=lambda **kw: None, decoder_factory=NativeDecoder):
    """Decode actual media anew. Return assessable observations and held visits."""
    number=int(video_id.removeprefix('video-')); source=Path(source)
    source_sha=file_sha(source)
    implementation_sha=digest({'observation_files':{p.name:file_sha(p) for p in HERE.iterdir() if p.suffix in ('.py','.swift','.json')},'producer':file_sha(Path(__file__))})
    with TemporaryDirectory(prefix='vyflare-observation-') as temporary:
        root=Path(temporary); progress(stage='Compiling Decoder',progress=0)
        decoder=decoder_factory(root)
        progress(stage='Decoding Event Frames',progress=5)
        events=decoder.decode('events',source,root/'events')
        observer=Observer(number,Config(**CONFIG)); previous=None
        for i,record in enumerate(events):
            with Image.open(root/'events'/(record['id']+'.jpg')) as image:
                features, previous=extract(np.asarray(image.convert('RGB')),previous)
            observer.step({'frame_id':record['id'],'video':number,'seconds':record['actual_seconds'],**features})
            if i%50==0: progress(stage='Detecting Fills',progress=10+int(65*i/len(events)))
        visits=[v for v in observer.finish_source()['observations'] if v['episodes']]
        progress(stage='Refining Dispense Timing',progress=76)
        visits=refine_visits(visits,events,root/'events',decoder,source,root/'timing',CONFIG)
        tasks=[]
        for i,visit in enumerate(visits):
            if visit['candidate_appearance_window_seconds']:
                tasks.extend({'id':f'fill_{i+1}_post_{j}','seconds':visit['candidate_appearance_window_seconds'][0]+offset}
                    for j,offset in enumerate((.05,.15,.25)))
        progress(stage='Measuring Final Appearance',progress=80)
        colors=decoder.decode('color',source,root/'color',tasks) if tasks else []
        decoded={r['id']:r for r in colors}
        if set(decoded)!={t['id'] for t in tasks}: raise ValueError('Decoder did not account for all requested samples')
        observations=[]; held=[]
        for i,visit in enumerate(visits):
            vial_id=f'V{number}-V{i+1:02}'; label=f'Video {number} · Vial {i+1}'
            intervals=[{'start':e['start_interval_seconds'],'end':e['end_interval_seconds']} for e in visit['episodes']]
            base={'video_id':video_id,'vial_id':vial_id,'label':label,'episodes':intervals}
            if any(e['end'] is None or not e['start'][1]<e['end'][0] for e in intervals):
                held.append({**base,'hold_reasons':sorted(set(visit['flags']+['INCOMPLETE_EVENT_INTERVALS']))}); continue
            reasons=list(visit['flags']); raw=None; frames=[]; times=[]; cadence=False
            window=visit['candidate_appearance_window_seconds']; departure=visit['departure_interval_seconds']
            if window:
                ids=[f'fill_{i+1}_post_{j}' for j in range(3)]
                raw,frames=measure_triplet([root/'color'/(key+'.png') for key in ids])
                times=[decoded[key]['actual_seconds'] for key in ids]
                cadence=(all(window[0]<t<window[1] for t in times)
                    and all(abs(decoded[t['id']]['actual_seconds']-t['seconds'])<=.067 for t in tasks if t['id'] in ids)
                    and all(a<b and abs((b-a)-.1)<=.034 for a,b in zip(times,times[1:])))
                for frame,t in zip(frames,times): frame['actual_seconds']=t
            phase=bool(departure and times and all(intervals[-1]['end'][1]<t<departure[0] for t in times))
            if raw is None or raw['temporal_distance']>2.24 or raw['region_distance']>2.45: reasons.append('COLOR_SAMPLING_UNRELIABLE')
            if not phase: reasons.append('POSTFILL_SAMPLE_PHASE_NOT_SUPPORTED')
            o={**base,'observation_id':PRODUCER_VERSION+':'+visit['observation_id'],'video':number,
                'source_kind':'FRESH_RECORDED_VIDEO_OBSERVATION','duration_bounds_seconds':[
                    [e['end'][0]-e['start'][1],e['end'][1]-e['start'][0]] for e in intervals],
                'source_episode_intervals':intervals,'raw_rgb':raw,'sample_actual_seconds':times,
                'departure_interval_seconds':departure,'candidate_appearance_window_seconds':window,
                'reference_cadence_and_window_check':cadence,'available_demo_checks_pass':not reasons,
                'hold_reasons':sorted(set(reasons)),'operational_eligibility':'NOT_VALIDATED',
                'source_lineage':{'video_sha256':source_sha,'detector_sha256':implementation_sha,
                    'config_sha256':digest(CONFIG),'frame_provenance':frames,'producer_version':PRODUCER_VERSION},
                'timing_refinement':visit['timing_refinement'],
                'identity_method':visit['identity_method'],'dispense_colors':None,'tank_sources':None,
                'physical_volume':None,'chemical_composition':None}
            observations.append(validate_observation(o))
        if file_sha(source)!=source_sha: raise ValueError('Source video changed during processing')
        progress(stage='Saving Recipe Assessments',progress=95)
        return {'observations':observations,'held_visits':held,'source_sha256':source_sha,
            'event_frame_count':len(events),'detected_fill_count':len(visits),'producer_version':PRODUCER_VERSION}


class RecordedVideoProducer:
    """One bounded worker; duplicate starts share the job, and writes are atomic."""
    def __init__(self, bank, video_root, runner=produce_video):
        self.bank=bank; self.video_root=Path(video_root); self.runner=runner
        self.lock=RLock(); self.jobs={}; self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='recorded-observer')

    def capability(self): return NativeDecoder.capability()

    def source(self, video_id):
        if video_id not in ('video-1','video-2'): raise KeyError('Unknown recorded video')
        path=self.video_root/f"vial_fill_{video_id.replace('-','_')}.mp4"
        if not path.is_file(): raise FileNotFoundError('Source recording is not installed on the backend')
        return path

    def saved(self, video_id):
        if video_id not in ('video-1','video-2'): raise KeyError('Unknown recorded video')
        return [r for r in self.bank.assessments() if r['observation'].get('source_kind')=='FRESH_RECORDED_VIDEO_OBSERVATION'
            and r['observation']['video_id']==video_id]

    def get(self, video_id):
        saved=self.saved(video_id)
        with self.lock: job=deepcopy(self.jobs.get(video_id,{'state':'saved' if saved else 'idle','progress':100 if saved else 0}))
        return {'video_id':video_id,**job,'assessments':saved}

    def start(self, video_id):
        path=self.source(video_id)
        if not self.capability()['available']: raise ValueError(self.capability()['reason'])
        with self.lock:
            if any(j['state']=='processing' for j in self.jobs.values()):
                if self.jobs.get(video_id,{}).get('state')=='processing': return self.get(video_id)
                raise RuntimeError('Another recording is processing; wait for it to finish')
            self.jobs[video_id]={'state':'processing','stage':'Queued','progress':0}
            self.executor.submit(self._run,path,video_id)
            return self.get(video_id)

    def _run(self, path, video_id):
        def progress(**values):
            with self.lock: self.jobs[video_id].update(values)
        try:
            result=self.runner(path,video_id,progress)
            # No partial bank writes if decode, features, phase or source validation fails.
            saved=self.bank.assess_many(result.pop('observations'))
            with self.lock: self.jobs[video_id].update(state='completed',stage='Complete',progress=100,
                **result,new_patterns=saved['new_patterns'],replayed_assessments=saved['replayed_assessments'])
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Recorded-video observation failed')
            with self.lock: self.jobs[video_id].update(state='failed',stage='Failed',
                error='Video processing failed. Check decoder availability, 640 × 480 geometry and backend logs. No partial run was saved.')

    def close(self): self.executor.shutdown(wait=True,cancel_futures=True)
