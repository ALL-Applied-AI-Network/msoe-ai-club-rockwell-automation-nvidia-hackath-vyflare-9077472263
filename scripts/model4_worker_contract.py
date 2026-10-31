"""Cosmos worker interface for model4/recipe-detection-backend-integration.

Register on the existing resident worker so no additional model is loaded.
"""
import hashlib
import tempfile
import time
import warnings
from pathlib import Path
from flask import jsonify,request

REFERENCE_BRANCH='model4/recipe-detection-backend-integration'
REFERENCE_COMMIT='956d5d24d19f80b99f85d4841e678d20d533e0fb'

def register_model4_worker(app,runtime,gate):
    @app.post('/backend/predict')
    def backend_predict():
        frame_id=request.form.get('frame_id','').strip()
        model=request.form.get('model','cosmos')
        prompt=request.form.get('prompt','Describe the visible scene briefly.').strip()
        def error(message,status):return jsonify(error=message,frame_id=frame_id),status
        if not frame_id or len(frame_id)>128:return error('frame_id must contain 1-128 characters',400)
        if model not in {'cosmos','cosmos_lite'}:return error('Worker model must be cosmos or cosmos_lite',400)
        if not prompt or len(prompt)>2000:return error('prompt must contain 1-2000 characters',400)
        upload=request.files.get('image')
        if upload is None:return error('image file is required',400)
        # Per-route image limit; existing /predict still accepts video uploads.
        if request.content_length is None or request.content_length>5*1024*1024:return error('Image request exceeds 5 MiB',413)
        execution=getattr(runtime,'execution',None)
        if not isinstance(execution,dict) or any(execution.get(k)!=v for k,v in {
                'system':'Linux','machine':'aarch64','gpu':'NVIDIA GB10'}.items()):
            return error('Verified DGX Spark execution metadata unavailable',503)
        if not gate.acquire(blocking=False):
            response,status=error('Inference busy; skip this frame',429)
            response.headers['Retry-After']='1';return response,status
        try:
            from PIL import Image,ImageOps,UnidentifiedImageError
            from io import BytesIO
            data=upload.read()
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter('error',Image.DecompressionBombWarning)
                    with Image.open(BytesIO(data)) as source:
                        if source.format not in {'JPEG','PNG'}:return error('Only JPEG and PNG images supported',415)
                        if source.width*source.height>16_000_000:return error('Image exceeds 16 million pixels',413)
                        source.load();image=ImageOps.exif_transpose(source).convert('RGB')
            except (Image.DecompressionBombError,Image.DecompressionBombWarning):return error('Image exceeds pixel limit',413)
            except (UnidentifiedImageError,OSError,ValueError):return error('Invalid or corrupt image',400)
            started=time.perf_counter()
            with tempfile.TemporaryDirectory(prefix='cosmos-model4-worker-') as directory:
                path=Path(directory)/'input.png';image.save(path)
                output=runtime.predict(path,'adapter',prompt_override=prompt)
            raw=output.get('outputs',{}).get('adapter',{}).get('raw_text')
            if not isinstance(raw,str):return error('Inference returned no text',500)
            return jsonify(frame_id=frame_id,model=model,mode='real',
                inference_ms=round((time.perf_counter()-started)*1000,1),
                result=dict(text=raw,execution=execution,implementation='cosmos3-nano-vial-lora',
                    model_identity=runtime.identity,prompt_applied=prompt,
                    image_sha256=hashlib.sha256(data).hexdigest(),
                    parsed_appearance=output['outputs']['adapter'].get('parsed'),
                    task_scope='Experimental appearance reasoning; not measured ingredients, dose, volume or a release decision',
                    safety=dict(provider=None,status='not_provided_by_this_lora_worker'),
                    integration_reference=dict(branch=REFERENCE_BRANCH,commit=REFERENCE_COMMIT)))
        except (ValueError,OSError) as exc:return error(str(exc),400)
        except Exception:
            app.logger.exception('Backend-compatible Cosmos inference failed')
            return error('Cosmos inference failed; see worker log',500)
        finally:gate.release()
