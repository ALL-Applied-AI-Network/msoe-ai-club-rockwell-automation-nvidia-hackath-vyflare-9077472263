"""Private-network browser tester for the Cosmos vial LoRA pilot."""
import argparse
import contextlib
import hashlib
import json
import logging
import tempfile
import threading
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request

VIDEO_EXTENSIONS={'.mp4','.mov','.avi','.mkv'}
IMAGE_EXTENSIONS={'.jpg','.jpeg','.png','.webp'}

HTML=r'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VyFlare vial model tester</title><style>
body{font:16px system-ui,sans-serif;background:#f3f5f8;color:#162234;margin:0}main{max-width:1050px;margin:40px auto;padding:0 24px}h1{margin-bottom:8px}p{line-height:1.5}.card{background:white;padding:24px;border-radius:14px;margin:20px 0;border:1px solid #dce2eb}label{display:block;font-weight:600;margin:14px 0 6px}input,select,textarea,button{font:inherit;box-sizing:border-box}input[type=text],select,textarea{padding:10px;width:100%;border:1px solid #9aa9bb;border-radius:6px}button{padding:11px 18px;background:#2151c5;color:white;border:0;border-radius:7px;cursor:pointer;margin:12px 8px 0 0}button:disabled{opacity:.5;cursor:wait}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f5f8;padding:16px;border-radius:8px}#status{font-weight:600}small{color:#526174}video,img{max-width:100%;max-height:320px;display:block;margin:16px 0}.hidden{display:none}@media(max-width:650px){.grid{grid-template-columns:1fr}}
</style><main><h1>VyFlare vial model tester</h1><p>Upload a vial clip to compare Cosmos3-Nano with the fine-tuned pilot adapter. Results describe visible color; they do not establish chemical identity or contamination.</p>
<section class="card"><form id="test"><label for="media">Vial video or photo</label><input id="media" type="file" accept="video/mp4,video/quicktime,video/x-msvideo,video/x-matroska,image/jpeg,image/png,image/webp" required><p><small>Use a short clip with one clearly identifiable target vial. Upload limit: 100 MiB. Videos use 32 sampled frames; brief changes can be missed. Photo mode is exploratory because the adapter was trained on videos.</small></p><div id="preview"></div><label for="mode">Model</label><select id="mode"><option value="compare">Compare base and fine-tuned</option><option value="adapter">Fine-tuned only</option><option value="base">Base only</option></select><button id="run">Run test</button></form><p id="status" role="status">Ready.</p></section>
<section id="results" class="card hidden"><h2>Result</h2><p id="details"></p><div class="grid"><div><h3>Base model</h3><pre id="base">Not requested</pre></div><div><h3>Fine-tuned adapter</h3><pre id="adapter">Not requested</pre></div></div><button id="download" type="button">Download result JSON</button><label for="reviewer">Reviewer name (optional)</label><input id="reviewer" type="text" maxlength="100"><label for="human">Your observed color sequence (optional)</label><input id="human" type="text" placeholder="For example: blue > dark green" maxlength="500"><label for="notes">Notes or uncertainty</label><textarea id="notes" rows="3" maxlength="2000"></textarea><button id="save" type="button">Save human feedback</button><p id="feedbackStatus" role="status"></p><small>Uploads are deleted after inference. Saving feedback stores the result, file hash/name, and your correction on the Spark; it does not automatically retrain the model. Download your result before leaving.</small></section>
<script>
let result=null,previewUrl=null;const el=id=>document.getElementById(id);el('media').onchange=()=>{el('preview').replaceChildren();if(previewUrl)URL.revokeObjectURL(previewUrl);const f=el('media').files[0];if(!f)return;previewUrl=URL.createObjectURL(f);const p=document.createElement(f.type.startsWith('image/')?'img':'video');p.src=previewUrl;if(p.tagName==='VIDEO')p.controls=true;el('preview').append(p)};
el('test').onsubmit=async e=>{e.preventDefault();const f=el('media').files[0];if(f.size>100*1024*1024){el('status').textContent='File exceeds 100 MiB.';return}el('run').disabled=true;el('results').classList.add('hidden');el('status').textContent='Analyzing on the Spark. A comparison runs both models in sequence; please keep this page open.';try{const form=new FormData();form.append('media',f);form.append('mode',el('mode').value);const r=await fetch('/predict',{method:'POST',body:form});const j=await r.json();if(!r.ok)throw Error(j.error||'Test failed');result=j;for(const name of ['base','adapter'])el(name).textContent=j.outputs[name]?JSON.stringify(j.outputs[name],null,2):'Not requested';el('details').textContent=j.media_kind+' · '+j.seconds.toFixed(1)+' seconds processing · '+j.run_id+(j.warning?' · '+j.warning:'');el('results').classList.remove('hidden');el('status').textContent='Test complete.';el('human').value='';el('notes').value='';el('feedbackStatus').textContent=''}catch(err){el('status').textContent=err.message}finally{el('run').disabled=false}};
el('download').onclick=()=>{if(!result)return;const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='vial-test-'+result.run_id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
el('save').onclick=async()=>{if(!result)return;el('save').disabled=true;try{const r=await fetch('/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({run_id:result.run_id,reviewer:el('reviewer').value,human_sequence:el('human').value,notes:el('notes').value})});const j=await r.json();if(!r.ok)throw Error(j.error);result.feedback=j.feedback;el('feedbackStatus').textContent='Feedback saved. Download again to include your correction.'}catch(e){el('feedbackStatus').textContent=e.message}finally{el('save').disabled=false}};
</script></main></html>'''


class ModelRuntime:
    def __init__(self,checkpoint,adapter):
        import torch
        from transformers import AutoProcessor,Qwen3VLForConditionalGeneration
        from peft import PeftModel
        self.torch=torch
        provenance=json.loads((checkpoint/'base_provenance.json').read_text())
        if provenance['source_model']!='nvidia/Cosmos3-Nano':
            raise ValueError('Expected extracted Cosmos3-Nano reasoner')
        self.processor=AutoProcessor.from_pretrained(checkpoint,local_files_only=True,fix_mistral_regex=True)
        base=Qwen3VLForConditionalGeneration.from_pretrained(checkpoint,dtype=torch.bfloat16,
            local_files_only=True,attn_implementation='sdpa').to('cuda')
        self.model=PeftModel.from_pretrained(base,adapter,is_trainable=False).eval()
        self.identity=dict(base_snapshot=provenance['source_snapshot'],adapter=str(adapter),frames=32,total_video_pixels=2621440)

    def predict(self,path,mode):
        import cv2
        import numpy as np
        from PIL import Image,ImageOps
        from prepare_spark_pilot import QUESTION
        is_video=path.suffix.lower() in VIDEO_EXTENSIONS
        if is_video:
            cap=cv2.VideoCapture(str(path))
            try:
                count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));fps=cap.get(cv2.CAP_PROP_FPS)
                if count<2 or fps<=0:raise ValueError('Could not decode this video.')
                if count/fps>600:raise ValueError('Use a clip shorter than 10 minutes, preferably under one minute.')
                indices=np.linspace(0,count-1,min(32,count)).round().astype(int).tolist();frames=[]
                for index in indices:
                    cap.set(cv2.CAP_PROP_POS_FRAMES,index);ok,frame=cap.read()
                    if not ok:raise ValueError('A sampled video frame could not be decoded.')
                    frames.append(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
                messages=[dict(role='user',content=[dict(type='video'),dict(type='text',text=QUESTION)])]
                text=self.processor.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
                encoded=self.processor(text=[text],videos=[np.stack(frames)],return_tensors='pt',videos_kwargs=dict(
                    do_sample_frames=False,video_metadata=[dict(total_num_frames=count,fps=fps,frames_indices=indices)],
                    size=dict(shortest_edge=2621440,longest_edge=2621440)))
                info=dict(kind='video',duration_seconds=count/fps,sampled_frames=len(indices),source_fps=fps)
            finally:cap.release()
        else:
            with Image.open(path) as source:
                if source.width*source.height>20000000:raise ValueError('Photo exceeds 20 megapixels.')
                image=ImageOps.exif_transpose(source).convert('RGB');image.thumbnail((1280,1280))
            prompt='Inspect the visible liquid in this single vial photo. Return only JSON with observed_color_sequence containing one observed color or shade. Do not infer past color changes from a still image.'
            messages=[dict(role='user',content=[dict(type='image'),dict(type='text',text=prompt)])]
            text=self.processor.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
            encoded=self.processor(text=[text],images=[image],return_tensors='pt',images_kwargs=dict(size=dict(shortest_edge=262144,longest_edge=262144)))
            info=dict(kind='photo',processed_width=image.width,processed_height=image.height)
        inputs={k:v.to('cuda') for k,v in encoded.items() if self.torch.is_tensor(v)}
        if inputs['input_ids'].shape[1]>8192:raise ValueError('Media exceeds the model token budget.')
        outputs={}
        for name in (['base','adapter'] if mode=='compare' else [mode]):
            context=self.model.disable_adapter() if name=='base' else contextlib.nullcontext()
            with context,self.torch.inference_mode():
                generated=self.model.generate(**inputs,max_new_tokens=96,do_sample=False,use_cache=True)
                raw=self.processor.batch_decode(generated[:,inputs['input_ids'].shape[1]:],skip_special_tokens=True)[0]
            parsed=None;clean=raw.strip()
            if clean.startswith('```'):clean=clean.split('\n',1)[-1].rsplit('```',1)[0].strip()
            try:
                parsed=json.loads(clean)
                colors=parsed['observed_color_sequence']
                if not isinstance(colors,list) or not colors or not all(isinstance(c,str) and c.strip() for c in colors):parsed=None
            except (ValueError,KeyError,TypeError):parsed=None
            outputs[name]=dict(raw_text=raw,parsed=parsed,valid_color_json=parsed is not None)
        return dict(outputs=outputs,media_info=info,media_kind=info['kind'],prompt=text)


def create_app(runtime,feedback_dir):
    app=Flask(__name__);app.config['MAX_CONTENT_LENGTH']=100*1024*1024
    gate=threading.Lock();records=OrderedDict();records_lock=threading.Lock()
    @app.get('/')
    def home():return HTML
    @app.get('/health')
    def health():return jsonify(ready=True,busy=gate.locked(),model=runtime.identity)
    @app.errorhandler(413)
    def too_large(error):return jsonify(error='Upload exceeds 100 MiB.'),413
    @app.post('/predict')
    def predict():
        mode=request.form.get('mode','compare');upload=request.files.get('media')
        if mode not in {'base','adapter','compare'}:return jsonify(error='Invalid model mode.'),400
        if upload is None or not upload.filename:return jsonify(error='Choose a video or photo.'),400
        suffix=Path(upload.filename).suffix.lower()
        if suffix not in VIDEO_EXTENSIONS|IMAGE_EXTENSIONS:return jsonify(error='Unsupported file extension.'),415
        if not gate.acquire(blocking=False):return jsonify(error='The Spark is processing another test. Please retry shortly.'),429
        try:
            started=time.time()
            with tempfile.TemporaryDirectory(prefix='vial-model-test-') as directory:
                path=Path(directory)/('input'+suffix);upload.save(path)
                with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
                result=runtime.predict(path,mode)
            result.update(run_id=uuid.uuid4().hex,created_at=datetime.now(timezone.utc).isoformat(),
                filename=Path(upload.filename).name,media_sha256=digest,seconds=time.time()-started,model=runtime.identity)
            if result['media_kind']=='photo':result['warning']='Exploratory photo mode; the adapter was trained on videos.'
            with records_lock:
                records[result['run_id']]=result
                while len(records)>100:records.popitem(last=False)
            return jsonify(result)
        except (ValueError,OSError) as error:return jsonify(error=str(error)),400
        except Exception:
            logging.exception('Inference failed')
            return jsonify(error='Inference failed on the Spark. Check its tester log.'),500
        finally:gate.release()
    @app.post('/feedback')
    def feedback():
        data=request.get_json(silent=True)
        if not isinstance(data,dict):return jsonify(error='Expected JSON feedback.'),400
        identity=data.get('run_id')
        with records_lock:original=records.get(identity) if isinstance(identity,str) else None
        if original is None:return jsonify(error='Result expired or unknown. Downloaded results remain available locally.'),404
        limits={'reviewer':100,'human_sequence':500,'notes':2000}
        if any(not isinstance(data.get(k,''),str) or len(data.get(k,''))>n for k,n in limits.items()):return jsonify(error='Feedback field is invalid or too long.'),400
        review={k:data.get(k,'').strip() for k in limits}
        if not review['human_sequence'] and not review['notes']:return jsonify(error='Enter a correction or note before saving.'),400
        review['saved_at']=datetime.now(timezone.utc).isoformat();review['status']='submitted_for_review_not_training_ground_truth'
        record=dict(original,feedback=review)
        feedback_dir.mkdir(parents=True,exist_ok=True)
        temp=feedback_dir/(identity+'.tmp');temp.write_text(json.dumps(record,indent=2),encoding='utf-8');temp.replace(feedback_dir/(identity+'.json'))
        return jsonify(saved=True,feedback=review)
    return app


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint',type=Path,required=True);parser.add_argument('--adapter',type=Path,required=True)
    parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=7865)
    parser.add_argument('--feedback-dir',type=Path,default=Path('outputs/tester-feedback'))
    args=parser.parse_args()
    runtime=ModelRuntime(args.checkpoint,args.adapter)
    from waitress import serve
    print(f'Model ready; serving on {args.host}:{args.port}',flush=True)
    serve(create_app(runtime,args.feedback_dir),host=args.host,port=args.port,threads=4)


if __name__=='__main__':main()
