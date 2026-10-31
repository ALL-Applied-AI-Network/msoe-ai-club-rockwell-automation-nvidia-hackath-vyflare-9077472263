"""Lightweight gateway to the existing Cosmos tester; no extra GPU model load."""
import argparse
import hashlib
import json
import uuid
from urllib.error import HTTPError,URLError
from urllib.request import Request,urlopen
from flask import Flask,jsonify,request
from cosmos_companion import validate_context,observation,combine_with_model4,SCHEMA

EXTENSIONS={'.mp4','.mov','.avi','.mkv','.jpg','.jpeg','.png','.webp'}

class WorkerError(Exception):
    def __init__(self,status,message):self.status=status;super().__init__(message)

class TesterClient:
    def __init__(self,url):self.url=url.rstrip('/')

    def _request(self,path,data=None,headers=None):
        try:
            with urlopen(Request(self.url+path,data=data,headers=headers or {}),timeout=300) as response:
                return json.load(response)
        except HTTPError as error:
            raise WorkerError(error.code if error.code in {400,413,415,429,503} else 502,'Cosmos worker rejected the request') from error
        except (URLError,TimeoutError,OSError,ValueError) as error:
            raise WorkerError(503,'Cosmos worker unavailable or returned invalid data') from error

    def health(self):return self._request('/health')

    def predict(self,data,suffix):
        # Metadata, recipe and label-bearing filenames are not sent to the worker.
        boundary='cosmos-'+uuid.uuid4().hex
        body=(f'--{boundary}\r\nContent-Disposition: form-data; name="mode"\r\n\r\nadapter\r\n'
              f'--{boundary}\r\nContent-Disposition: form-data; name="media"; filename="input{suffix}"\r\n'
              'Content-Type: application/octet-stream\r\n\r\n').encode()+data+f'\r\n--{boundary}--\r\n'.encode()
        return self._request('/predict',body,{'Content-Type':'multipart/form-data; boundary='+boundary})

def create_app(client):
    app=Flask(__name__);app.config['MAX_CONTENT_LENGTH']=100*1024*1024
    @app.errorhandler(413)
    def too_large(error):return jsonify(error='Upload exceeds 100 MiB.'),413
    @app.errorhandler(WorkerError)
    def worker_error(error):return jsonify(error=str(error)),error.status

    @app.get('/health')
    def health():
        worker=client.health()
        return jsonify(ready=worker.get('ready') is True,busy=worker.get('busy'),
            role='cosmos_appearance_companion',schema_version=SCHEMA,worker_model=worker.get('model'),
            extra_gpu_model_loaded=False)

    @app.post('/v1/cosmos/observe')
    def observe():
        from pathlib import Path
        try:
            context=validate_context(json.loads(request.form.get('context','null')))
            upload=request.files.get('media')
            if upload is None or not upload.filename:raise ValueError('media is required')
            suffix=Path(upload.filename).suffix.lower()
            if suffix not in EXTENSIONS:return jsonify(error='Unsupported media extension'),415
            media=upload.read()
            if not media:raise ValueError('Media is empty')
            digest=hashlib.sha256(media).hexdigest()
            result=client.predict(media,suffix)
            try:return jsonify(observation(result,context,digest))
            except (ValueError,KeyError,TypeError):return jsonify(error='Cosmos worker response failed the evidence contract'),502
        except (ValueError,KeyError,TypeError) as error:return jsonify(error=str(error)),400

    @app.post('/v1/cosmos/combine-model4')
    def combine():
        try:
            data=request.get_json(silent=True)
            if not isinstance(data,dict):raise ValueError('Expected JSON object')
            return jsonify(combine_with_model4(data.get('cosmos'),data.get('model4')))
        except (ValueError,KeyError,TypeError) as error:return jsonify(error=str(error)),400
    return app

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--worker-url',default='http://127.0.0.1:7865');p.add_argument('--host',default='127.0.0.1')
    p.add_argument('--port',type=int,default=7866)
    args=p.parse_args()
    from waitress import serve
    print('Cosmos companion gateway; inference remains on existing worker',flush=True)
    serve(create_app(TesterClient(args.worker_url)),host=args.host,port=args.port,threads=4)

if __name__=='__main__':main()
