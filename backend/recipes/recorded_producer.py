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

from .recording_sources import RecordingSources
from .inspection_log import playback_events, observation_events, completion_time, clarify_saved_outcomes
from .demo_store import digest, validate_observation
from .observation.features import extract
from .observation.trace import Config, Observer
from .observation.refine import refine_visits
from .geometry_tracking import GeometryTracker, detect_vials, IMPLEMENTATION_SHA as GEOMETRY_SHA
from .recorded_eligibility import build_report, evaluate as geometry_eligibility, POLICY_SHA

HERE = Path(__file__).with_name('observation')
CONFIG = json.loads((HERE/'config.json').read_text())
PRODUCER_VERSION = 'fixed-station-native/4'
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
    number=int(video_id.removeprefix('video-')) if video_id.startswith('video-') else int(video_id.removeprefix('recording-')[:12],16); source=Path(source)
    source_sha=file_sha(source)
    implementation_sha=digest({'observation_files':{p.name:file_sha(p) for p in HERE.iterdir() if p.suffix in ('.py','.swift','.json')},'producer':file_sha(Path(__file__)),'geometry':GEOMETRY_SHA,'eligibility':POLICY_SHA})
    with TemporaryDirectory(prefix='vyflare-observation-') as temporary:
        root=Path(temporary); progress(stage='Compiling Decoder',progress=0)
        decoder=decoder_factory(root)
        progress(stage='Decoding Event Frames',progress=5)
        events=decoder.decode('events',source,root/'events')
        observer=Observer(number,Config(**CONFIG)); previous=None
        geometry=GeometryTracker();geometry_frames=[]
        for i,record in enumerate(events):
            with Image.open(root/'events'/(record['id']+'.jpg')) as image:
                pixels=np.asarray(image.convert('RGB'))
                features, previous=extract(pixels,previous)
            geometry_frames.append({**geometry.step(pixels,record['actual_seconds']),'frame_id':record['id'],
                'sha256':file_sha(root/'events'/(record['id']+'.jpg'))})
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
            vial_id=f'V{number}-V{i+1:02}'; label=f'Video {number} · Vial {i+1}' if video_id.startswith('video-') else f'Opened Recording · Vial {i+1}'
            intervals=[{'start':e['start_interval_seconds'],'end':e['end_interval_seconds']} for e in visit['episodes']]
            base={'video_id':video_id,'vial_id':vial_id,'label':label,'episodes':intervals}
            if any(e['end'] is None or not e['start'][1]<e['end'][0] for e in intervals):
                held.append({**base,'available_at':events[-1]['actual_seconds'],'hold_reasons':sorted(set(visit['flags']+['INCOMPLETE_EVENT_INTERVALS']))}); continue
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
            colour_checks=[]
            for frame in frames:
                path=root/'color'/(frame['evidence_id']+'.png')
                with Image.open(path) as image:
                    detections=detect_vials(np.asarray(image.convert('RGB')));dimensions=list(image.size)
                box=next((d['box'] for d in detections if d['position']=='Filling Position'),None)
                colour_checks.append({'frame_id':frame['evidence_id'],'sha256':frame['sha256'],
                    'actual_seconds':frame['actual_seconds'],'dimensions':dimensions,'box':box})
            o['recorded_geometry']=build_report(o,geometry_frames,colour_checks,source_sha)
            observations.append(validate_observation(o))
        if file_sha(source)!=source_sha: raise ValueError('Source video changed during processing')
        progress(stage='Saving Recipe Assessments',progress=95)
        return {'observations':observations,'held_visits':held,'source_sha256':source_sha,
            'event_frame_count':len(events),'detected_fill_count':len(visits),'producer_version':PRODUCER_VERSION,
            'analyzed_through_seconds':events[-1]['actual_seconds'],'geometry_frames':geometry_frames,'tracking_held_count':sum(geometry_eligibility(o)['status']=='HELD' for o in observations)}


class RecordedVideoProducer:
    """One bounded worker; duplicate starts share the job, and writes are atomic."""
    def __init__(self, bank, video_root, runner=produce_video, geometry_service=None, upload_root=None):
        self.bank=bank; self.video_root=Path(video_root); self.runner=runner; self.geometry_service=geometry_service
        self.sources=RecordingSources(video_root, upload_root or Path(video_root)/".recordings")
        with bank.lock:database_path=bank.connection.execute('PRAGMA database_list').fetchone()[2]
        self.log_root=self.sources.uploads/('logs-'+hashlib.sha256(str(database_path).encode()).hexdigest()[:16])
        self.lock=RLock(); self.jobs={}; self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='recorded-observer')

    def capability(self): return NativeDecoder.capability()

    def source(self, video_id): return self.sources.source(video_id)

    def _journal(self, video_id):
        return self.log_root/(file_sha(self.source(video_id))+'.json')

    def _bank_fingerprint(self, video_id):
        source_sha=file_sha(self.source(video_id))
        with self.bank.lock:
            rows=self.bank.connection.execute('SELECT observation_key,evidence_hash,result FROM demo_assessments WHERE observation_key LIKE ? ORDER BY observation_key',(source_sha+':%',)).fetchall()
        return digest(rows)

    def saved(self, video_id):
        source_sha=file_sha(self.source(video_id))
        return [r for r in self.bank.assessments() if r['observation'].get('source_kind')=='FRESH_RECORDED_VIDEO_OBSERVATION'
            and r['observation']['video_id']==video_id and r['observation']['source_lineage']['video_sha256']==source_sha]

    def get(self, video_id):
        saved=self.saved(video_id)
        with self.lock:
            job=deepcopy(self.jobs.get(video_id,{'state':'saved' if saved else 'idle','progress':100 if saved else 0}))
            if job.get('source_sha256') and job['source_sha256']!=file_sha(self.source(video_id)) and job['state'] not in ('processing','queued'):
                self.jobs.pop(video_id,None);job={'state':'saved' if saved else 'idle','progress':100 if saved else 0}
        journal=self._journal(video_id)
        events=job.pop('events',None); analyzed=job.get('analyzed_through_seconds',0)
        if events is not None:pass
        elif journal.exists():
            cached=json.loads(journal.read_text())
            if cached.get('bank_fingerprint')==self._bank_fingerprint(video_id):
                events=cached['events'];analyzed=cached.get('analyzed_through_seconds',0)
                if job['state'] in ('idle','saved'):job={**cached['job'],'stage':'Saved Analysis','progress':100}
        if events is None and saved:
            # Original stored decisions, not memberships projected using future fills.
            baseline={r['observation_id']:r for r in self.bank.baseline_assessments()}
            events=sorted([e for r in saved for e in observation_events(baseline[r['observation_id']])],key=lambda e:(e['at'],e['id']))
            analyzed=max((e['at'] for e in events),default=0)
        if events and any(e.get('kind')=='recipe' and e.get('title')=='Unresolved' for e in events):
            # Presentation-only upgrade of old journals; do not reprocess footage,
            # rewrite assessments, or project memberships learned from later fills.
            source_sha=file_sha(self.source(video_id))
            original=[r for r in self.bank.baseline_assessments()
                if r['observation'].get('source_lineage',{}).get('video_sha256')==source_sha]
            events=clarify_saved_outcomes(events,original)
        return {'video_id':video_id,**job,'assessments':saved,'events':events or [],'analyzed_through_seconds':analyzed,
            'source_sha256':file_sha(self.source(video_id))}

    def ensure(self, video_id):
        with self.lock:
            value=self.get(video_id)
            if value['state'] in ('processing','queued','completed','saved'):return value
            if value['state']=='failed':return value
            return self.start(video_id,queue=True)


    def start(self, video_id, *, queue=False):
        path=self.source(video_id)
        if not self.capability()['available']: raise ValueError(self.capability()['reason'])
        with self.lock:
            if self.jobs.get(video_id,{}).get('state') in ('processing','queued'):return self.get(video_id)
            active=sum(j['state'] in ('queued','processing') for j in self.jobs.values())
            if active and not queue:raise RuntimeError('Another recording is processing; wait for it to finish')
            if active>=4:raise RuntimeError('The recording queue is full; retry after a recording finishes')
            self.jobs[video_id]={'state':'queued' if queue else 'processing','stage':'Queued','progress':0,'source_sha256':file_sha(path)}
            self.executor.submit(self._run,path,video_id)
            return self.get(video_id)

    def _run(self, path, video_id):
        def progress(**values):
            with self.lock: self.jobs[video_id].update(values)
        try:
            progress(state="processing")
            expected_sha=self.jobs[video_id]['source_sha256']
            if file_sha(path)!=expected_sha:raise ValueError('Source changed while queued')
            result=self.runner(path,video_id,progress)
            if file_sha(path)!=expected_sha or result.get('source_sha256',expected_sha)!=expected_sha:raise ValueError('Source changed during analysis')
            geometry_frames=result.pop('geometry_frames',None)
            if geometry_frames is not None and self.geometry_service is not None:
                self.geometry_service.publish(video_id,path,result['source_sha256'],geometry_frames)
            # No partial bank writes if decode, features, phase or source validation fails.
            self.log_root.mkdir(parents=True,exist_ok=True)
            journal=self._journal(video_id);temporary=journal.with_suffix('.tmp')
            # A log preparation failure rolls back the associated recipe writes.
            with self.bank.transaction():
                saved=self.bank.assess_many(result.pop('observations'),capture_timeline=True)
                events=playback_events(saved.pop('playback_snapshots'),result.get('held_visits',[]))
                completed={**self.jobs[video_id], 'state':'completed','stage':'Complete','progress':100,
                    **result,'new_patterns':saved['new_patterns'],'replayed_assessments':saved['replayed_assessments']}
                temporary.write_text(json.dumps({'events':events,'analyzed_through_seconds':result.get('analyzed_through_seconds',max((e['at'] for e in events),default=0)),
                    'job':completed,'bank_fingerprint':self._bank_fingerprint(video_id)},allow_nan=False))
            try:temporary.replace(journal)
            except OSError:
                completed['cache_warning']='Analysis saved; playback log is available for this session but its disk cache could not be published.'
                temporary.unlink(missing_ok=True)
            with self.lock:self.jobs[video_id]={**completed,'events':events}

        except Exception:
            import logging
            logging.getLogger(__name__).exception('Recorded-video observation failed')
            with self.lock: self.jobs[video_id].update(state='failed',stage='Failed',
                error='Video processing failed. Check decoder availability, 640 × 480 geometry and backend logs. No partial run was saved.')

    def close(self): self.executor.shutdown(wait=True,cancel_futures=True)
