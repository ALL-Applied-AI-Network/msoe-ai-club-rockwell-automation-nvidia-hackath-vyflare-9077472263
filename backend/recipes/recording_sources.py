"""Content-addressed local recordings; filenames never select server paths."""
import hashlib
import json
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock
from urllib.parse import unquote

MAX_UPLOAD = 128 * 1024 * 1024
MAX_STORAGE = 512 * 1024 * 1024
UPLOAD_ID = re.compile(r'recording-[0-9a-f]{64}\Z')
VIDEO_ID = re.compile(r'video-[1-5]\Z')
TYPES = {'video/mp4': '.mp4', 'video/webm': '.webm', 'video/quicktime': '.mov'}

class RecordingSources:
    def __init__(self, installed, uploads):
        self.installed=Path(installed); self.uploads=Path(uploads); self.lock=RLock()

    def source(self, key):
        if VIDEO_ID.fullmatch(key):
            path=self.installed/f"vial_fill_{key.replace('-', '_')}.mp4"
        elif UPLOAD_ID.fullmatch(key):
            meta=self.uploads/(key+'.json')
            if not meta.is_file() or meta.is_symlink(): raise KeyError('Unknown recording')
            value=json.loads(meta.read_text())
            if value.get('content_type') not in TYPES or value.get('sha256')!=key.removeprefix('recording-'): raise ValueError('Invalid recording registration')
            path=self.uploads/(key+TYPES[value['content_type']])
        else: raise KeyError('Unknown recording')
        if not path.is_file() or path.is_symlink(): raise FileNotFoundError('Recording is not installed')
        return path

    def register(self, stream, content_type, name):
        if content_type not in TYPES: raise ValueError('Use an MP4, MOV or WebM recording')
        name=Path(unquote(name).replace('\\','/')).name[:160] or 'Opened Recording'
        self.uploads.mkdir(parents=True,exist_ok=True,mode=0o700)
        with self.lock:
            used=sum(p.stat().st_size for p in self.uploads.glob('recording-*') if p.is_file())
            if used>=MAX_STORAGE:
                raise OverflowError('Recording storage is full; ask the operator to archive unused recordings')
            temporary=None
            try:
                with NamedTemporaryFile(dir=self.uploads,prefix='.upload-',delete=False) as f:
                    temporary=Path(f.name);digest=hashlib.sha256();size=0
                    while chunk:=stream.read(1024*1024):
                        size+=len(chunk)
                        if size>MAX_UPLOAD: raise OverflowError('Recording exceeds the 128 MiB upload limit')
                        if used+size>MAX_STORAGE:raise OverflowError('Recording storage limit exceeded')
                        digest.update(chunk);f.write(chunk)
                if not size: raise ValueError('Recording is empty')
                sha=digest.hexdigest()
                # Opening a second copy of an installed recording preserves source identity.
                for n in range(1,6):
                    p=self.installed/f'vial_fill_video_{n}.mp4'
                    if p.is_file() and p.stat().st_size==size:
                        h=hashlib.sha256()
                        with p.open('rb') as source:
                            for c in iter(lambda:source.read(1024*1024),b''):h.update(c)
                        if h.hexdigest()==sha:return {'video_id':f'video-{n}','sha256':sha,'name':name,'size':size}
                key='recording-'+sha;target=self.uploads/(key+TYPES[content_type])
                meta=self.uploads/(key+'.json')
                if meta.exists():
                    return {'video_id':key,'sha256':sha,'name':name,'size':size}
                temporary.replace(target);temporary=None
                value={'video_id':key,'sha256':sha,'name':name,'size':size,'content_type':content_type}
                with NamedTemporaryFile(dir=self.uploads,prefix='.metadata-',mode='w',delete=False) as f:
                    json.dump(value,f);metadata=Path(f.name)
                metadata.replace(meta)
                return value
            finally:
                if temporary is not None:temporary.unlink(missing_ok=True)
