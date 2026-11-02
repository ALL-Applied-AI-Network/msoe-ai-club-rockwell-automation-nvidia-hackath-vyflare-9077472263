"""Bounded pixel tracking sessions and recorded geometry sidecars; no recipe writes."""
import base64
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock
from time import monotonic
from uuid import uuid4

from flask import Blueprint, jsonify, request
import numpy as np
from PIL import Image, UnidentifiedImageError

from .geometry_tracking import CONFIG, VERSION, IMPLEMENTATION_SHA, GeometryTracker


def observation_geometry(observation,frames):
    start=observation['source_episode_intervals'][0]['start'][0]
    end=(observation.get('departure_interval_seconds') or [start,start])[0]
    samples=[f for f in frames if start<=f['captured_at']<end]
    tracked=[f for f in samples if any(d['position']=='Filling Position' and d['status']=='TRACKING' for d in f['detections'])]
    surfaces=[f for f in tracked if any(d['position']=='Filling Position' and d['surface'] is not None for d in f['detections'])]
    ids=sorted({d['track_id'] for f in tracked for d in f['detections'] if d['position']=='Filling Position'})
    recoveries=[e for f in samples for e in f.get('identity_events',[]) if e['event']=='DETECTION_LOSS_REASSOCIATED']
    resets=[e for f in samples for e in f.get('identity_events',[]) if e['event']=='DETECTION_LOSS_IDENTITY_RESET']
    return {'vial_id':observation.get('vial_id'),'observation_id':observation['observation_id'],
            'sample_count':len(samples),'tracked_samples':len(tracked),'visible_surface_samples':len(surfaces),
            'track_ids':ids,'bounded_detection_recoveries':recoveries,'identity_reset_events':resets,
            'identity_continuous':len(ids)==1 and len(tracked)==len(samples) and bool(samples),
            'issues':(['TRACK_ID_CHANGED_WITHIN_FILL'] if len(ids)>1 else [])+(['TRACKING_VISIBILITY_GAPS'] if len(tracked)<len(samples) else [])+(['NO_GEOMETRY_SAMPLES'] if not samples else []),
            'status':'SUPPLEMENTAL_EXPERIMENTAL_EVIDENCE','affects_recipe_decision':False}


class GeometryService:
    def __init__(self,video_root,cache_root,bank=None):
        self.source_resolver=None
        self.video_root=Path(video_root);self.cache_root=Path(cache_root);self.bank=bank
        self.lock=RLock();self.sessions={};self.jobs={};self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='pixel-geometry')
    def close(self):self.executor.shutdown(wait=True)
    def create_session(self):
        with self.lock:
            now=monotonic()
            self.sessions={k:v for k,v in self.sessions.items() if now-v['touched']<300}
            if len(self.sessions)>=8:raise RuntimeError('Tracking session limit reached; close an unused session or retry later')
            key=uuid4().hex;self.sessions[key]={'tracker':GeometryTracker(),'touched':now};return key
    def delete_session(self,key):
        with self.lock:self.sessions.pop(key,None)
    def frame(self,key,pixels,seconds):
        with self.lock:
            session=self.sessions.get(key)
            if session is None or monotonic()-session['touched']>=300:
                self.sessions.pop(key,None);raise KeyError('Tracking session expired; reconnect tracking')
            result=session['tracker'].step(pixels,seconds);session['touched']=monotonic();return result
    def source(self,video):
        if self.source_resolver is not None:return self.source_resolver(video)
        if video not in ('video-1','video-2'):raise KeyError('Unsupported recording')
        source=self.video_root/f"vial_fill_{video.replace('-','_')}.mp4"
        if not source.is_file():raise FileNotFoundError('Source recording is not installed')
        return source
    def get(self,video):
        source=self.source(video);stat=source.stat();revision=[stat.st_size,stat.st_mtime_ns]
        with self.lock:
            saved=self.jobs.get(video)
            if saved and saved.get('state')=='complete' and saved.get('source_revision')!=revision:
                self.jobs.pop(video,None)
            result=deepcopy(self.jobs.get(video,{'state':'idle','frames':[]}))
        if self.bank and result.get('state')=='complete':
            result['observations']=[observation_geometry(a['observation'],result['frames']) for a in self.bank.assessments()
                                    if a['observation'].get('source_kind')=='FRESH_RECORDED_VIDEO_OBSERVATION' and a['observation'].get('video_id')==video and a['observation'].get('source_lineage',{}).get('video_sha256')==result['source_sha256']]
        return result
    def start(self,video):
        source=self.source(video)
        from .recorded_producer import NativeDecoder
        if not NativeDecoder.capability()['available']:raise ValueError(NativeDecoder.capability()['reason'])
        current=self.get(video)
        with self.lock:
            if current.get('state') in ('processing','complete'):return current
            self.jobs[video]={'state':'processing','progress':0,'frames':[]}
            self.executor.submit(self._run,video,source)
        return self.get(video)
    def publish(self,video,source,source_sha,frames):
        """Publish the producer's same-pass geometry; never derive recipe decisions from this cache."""
        from .recorded_producer import file_sha
        if Path(source).resolve()!=self.source(video).resolve() or file_sha(source)!=source_sha:
            raise ValueError('Recorded geometry source changed')
        if not frames or any(f['version']!=VERSION for f in frames):raise ValueError('Recorded geometry revision mismatch')
        result={'state':'complete','progress':100,'version':VERSION,'implementation_sha256':IMPLEMENTATION_SHA,
                'source_sha256':source_sha,'frames':deepcopy(frames),'recipe_writes':0}
        self.cache_root.mkdir(parents=True,exist_ok=True)
        cache=self.cache_root/(video+'-'+source_sha[:16]+'-'+IMPLEMENTATION_SHA[:12]+'.json')
        temporary=cache.with_name(cache.name+'.'+uuid4().hex+'.tmp')
        try:
            temporary.write_text(json.dumps(result,allow_nan=False));temporary.replace(cache)
        finally:temporary.unlink(missing_ok=True)
        stat=Path(source).stat();result['source_revision']=[stat.st_size,stat.st_mtime_ns]
        with self.lock:self.jobs[video]=result

    def _run(self,video,source):
        from .recorded_producer import NativeDecoder,file_sha
        try:
            source_sha=file_sha(source);cache=self.cache_root/(video+'-'+source_sha[:16]+'-'+IMPLEMENTATION_SHA[:12]+'.json')
            if cache.exists():
                result=json.loads(cache.read_text())
                if result['source_sha256']!=source_sha or result['version']!=VERSION or result['implementation_sha256']!=IMPLEMENTATION_SHA:raise ValueError('Geometry cache provenance mismatch')
            else:
                with TemporaryDirectory(prefix='vial-geometry-') as temporary:
                    root=Path(temporary);decoder=NativeDecoder(root);records=decoder.decode('events',source,root/'events')
                    tracker=GeometryTracker();frames=[]
                    for i,r in enumerate(records):
                        with Image.open(root/'events'/(r['id']+'.jpg')) as image:pixels=np.asarray(image.convert('RGB'))
                        frames.append({**tracker.step(pixels,r['actual_seconds']),'frame_id':r['id']})
                        if i%40==0:
                            with self.lock:self.jobs[video]['progress']=int(100*i/len(records))
                    if file_sha(source)!=source_sha:raise ValueError('Source recording changed while tracking')
                    result={'state':'complete','progress':100,'version':VERSION,'implementation_sha256':IMPLEMENTATION_SHA,'source_sha256':source_sha,'frames':frames,'recipe_writes':0}
                    self.cache_root.mkdir(parents=True,exist_ok=True)
                    temporary_path=cache.with_name(cache.name+'.'+uuid4().hex+'.tmp')
                    try:
                        temporary_path.write_text(json.dumps(result,allow_nan=False));temporary_path.replace(cache)
                    finally:temporary_path.unlink(missing_ok=True)
            if file_sha(source)!=source_sha:raise ValueError('Source recording changed while loading geometry')
            stat=source.stat();result['source_revision']=[stat.st_size,stat.st_mtime_ns]
            with self.lock:self.jobs[video]=result
        except Exception as exc:
            with self.lock:self.jobs[video]={'state':'failed','error':str(exc),'frames':[]}


def create_geometry_blueprint(service):
    bp=Blueprint('geometry_api',__name__,url_prefix='/api/geometry')
    @bp.errorhandler(ValueError)
    @bp.errorhandler(TypeError)
    def invalid(exc):return jsonify(error=str(exc)),400
    @bp.errorhandler(KeyError)
    @bp.errorhandler(FileNotFoundError)
    def missing(exc):return jsonify(error=str(exc)),404
    @bp.errorhandler(RuntimeError)
    def busy(exc):return jsonify(error=str(exc)),409
    @bp.get('/status')
    def status():return jsonify(available=True,config=CONFIG,recipe_writes=0)
    @bp.post('/sessions')
    def create():
        if request.get_json()!={}:raise ValueError('Send an empty JSON object')
        return jsonify(session_id=service.create_session(),config=CONFIG),201
    @bp.delete('/sessions/<key>')
    def remove(key):service.delete_session(key);return '',204
    @bp.post('/sessions/<key>/frame')
    def frame(key):
        data=request.get_json()
        if not isinstance(data,dict) or set(data)!={'image','captured_at'}:raise ValueError('Provide image and captured_at only')
        encoded=data['image']
        if not isinstance(encoded,str) or len(encoded)>700000 or not encoded.startswith('data:image/jpeg;base64,'):
            raise ValueError('Provide a bounded JPEG data URL')
        try:
            raw=base64.b64decode(encoded.split(',',1)[1],validate=True)
            with Image.open(BytesIO(raw)) as image:
                if image.format!='JPEG' or image.size!=(640,480):raise ValueError('Tracking requires the original 640 × 480 station image')
                pixels=np.asarray(image.convert('RGB'))
        except (UnidentifiedImageError,OSError,base64.binascii.Error) as exc:raise ValueError('Invalid tracking image') from exc
        return jsonify(service.frame(key,pixels,data['captured_at']))
    @bp.route('/recordings/<video>',methods=['GET','POST'])
    def recording(video):
        if request.method=='POST':
            if request.get_json()!={}:raise ValueError('Send an empty JSON object')
            return jsonify(service.start(video)),202
        return jsonify(service.get(video))
    return bp
