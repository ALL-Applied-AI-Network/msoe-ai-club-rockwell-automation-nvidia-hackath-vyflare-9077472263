"""Single-Spark BF16 LoRA pilot on strictly extracted Cosmos3-Nano reasoner.

Uses HF/PEFT directly in the existing Spark environment; no full-model updates.
The validation partition is within one recording session, not an independent test.
"""
import argparse
import copy
import hashlib
import json
import math
import random
import time
from functools import lru_cache
from pathlib import Path


def score_predictions(predictions):
    valid=sequence=final=0
    for row in predictions:
        expected=json.loads(row['target'])['observed_color_sequence']
        try:
            text=row['prediction'].strip()
            if text.startswith('```'):
                text=text.split('\n',1)[1].rsplit('```',1)[0].strip()
            predicted=json.loads(text)['observed_color_sequence']
            if not isinstance(predicted,list) or not predicted or not all(isinstance(x,str) and x.strip() for x in predicted):
                raise ValueError('Not a color list')
            normalize=lambda colors:[c.strip().casefold() for c in colors]
            a,b=normalize(predicted),normalize(expected)
            valid+=1;sequence+=a==b;final+=a[-1]==b[-1]
        except (ValueError,KeyError,TypeError):
            pass
    n=len(predictions)
    return dict(n=n,valid_json=valid,sequence_exact=sequence,final_label_exact=final,
                sequence_exact_rate=sequence/n if n else None,final_label_exact_rate=final/n if n else None)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint',type=Path,required=True)
    parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--steps',type=int,default=20)
    parser.add_argument('--frames',type=int,default=32)
    parser.add_argument('--max-pixels',type=int,default=2621440,help='Total video pixel budget, not per-frame; default 32 x 81920')
    parser.add_argument('--accumulation',type=int,default=4)
    parser.add_argument('--eval-limit',type=int,default=0)
    parser.add_argument('--preflight',action='store_true')
    args=parser.parse_args()
    if args.output.exists():
        parser.error('Output exists; choose a new experiment version')
    if args.steps<1 or args.frames<2 or args.accumulation<1:
        parser.error('Invalid training budget')
    import cv2
    import numpy as np
    import torch
    from transformers import AutoProcessor,Qwen3VLForConditionalGeneration
    provenance=json.loads((args.checkpoint/'base_provenance.json').read_text())
    if provenance['source_model']!='nvidia/Cosmos3-Nano':
        raise ValueError('Expected extracted Cosmos3-Nano weights with provenance')
    description=json.loads((args.data/'experiment.json').read_text())
    train=json.loads((args.data/'train.json').read_text())
    val=json.loads((args.data/'val.json').read_text())
    if {r['recipe_id'] for r in train}&{r['recipe_id'] for r in val}:
        raise ValueError('Recipe-group overlap')
    for row in train+val:
        path=(args.data/row['media']).resolve()
        if not path.is_relative_to(args.data.resolve()):
            raise ValueError('Media path escapes dataset')
        with path.open('rb') as stream:
            actual=hashlib.file_digest(stream,'sha256').hexdigest()
        if actual!=row['sha256']:
            raise ValueError(f"Changed media: {row['id']}")
    processor=AutoProcessor.from_pretrained(args.checkpoint,local_files_only=True,fix_mistral_regex=True)
    random.seed(42);np.random.seed(42);torch.manual_seed(42)

    @lru_cache(maxsize=30)
    def video(relative):
        cap=cv2.VideoCapture(str(args.data/relative))
        try:
            count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));fps=cap.get(cv2.CAP_PROP_FPS)
            if count<2 or fps<=0:
                raise ValueError('Undecodable video')
            indices=np.linspace(0,count-1,min(args.frames,count)).round().astype(int).tolist()
            frames=[]
            for index in indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES,index)
                ok,frame=cap.read()
                if not ok:
                    raise ValueError(f'Cannot decode frame {index} in {relative}')
                frames.append(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
            return np.stack(frames),dict(total_num_frames=count,fps=fps,frames_indices=indices)
        finally:
            cap.release()

    def encode(row,with_answer):
        frames,metadata=video(row['media'])
        messages=[dict(role='user',content=[dict(type='video'),dict(type='text',text=row['question'])])]
        prompt=processor.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
        make_kwargs=lambda:dict(videos=[frames],return_tensors='pt',videos_kwargs=dict(
            do_sample_frames=False,video_metadata=[copy.deepcopy(metadata)],
            size=dict(shortest_edge=args.max_pixels,longest_edge=args.max_pixels)))
        prefix=processor(text=[prompt],**make_kwargs())
        if not with_answer:
            return {k:v for k,v in prefix.items() if torch.is_tensor(v)}
        messages.append(dict(role='assistant',content=row['answer']))
        text=processor.apply_chat_template(messages,tokenize=False,add_generation_prompt=False)
        full=processor(text=[text],**make_kwargs())
        length=prefix['input_ids'].shape[1]
        if not torch.equal(prefix['input_ids'],full['input_ids'][:,:length]):
            difference=(prefix['input_ids']!=full['input_ids'][:,:length]).nonzero()[0,1].item()
            print('PROCESSOR',type(processor).__name__,'DIFFERENCE',difference,'PROMPT',repr(prompt[-160:]),'FULL',repr(text[-200:]),flush=True)
            raise ValueError('Assistant-loss boundary does not match prompt prefix')
        labels=full['input_ids'].clone();labels[:,:length]=-100
        if (labels!=-100).sum()==0 or full['input_ids'].shape[1]>8192:
            raise ValueError('Empty target or token budget exceeded')
        full={k:v for k,v in full.items() if torch.is_tensor(v)}
        full['labels']=labels
        return full

    first=encode(train[0],True)
    print(json.dumps(dict(event='data_preflight_passed',tokens=int(first['input_ids'].shape[1]),
        supervised_tokens=int((first['labels']!=-100).sum()),video_grid=first['video_grid_thw'].tolist(),frames=args.frames,train=len(train),val=len(val))),flush=True)
    if args.preflight:
        return
    if not torch.cuda.is_available():
        raise RuntimeError('GPU training must run on Spark CUDA')
    args.output.mkdir(parents=True)
    started=time.time()
    import peft,transformers,platform
    record=dict(arguments={k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()},
        dataset=description,base=provenance,versions=dict(torch=torch.__version__,transformers=transformers.__version__,
        peft=peft.__version__,python=platform.python_version()),gpu=torch.cuda.get_device_name(0),seed=42,
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),status='loading')
    def status(state,**values):
        record.update(status=state,elapsed_seconds=time.time()-started,**values)
        (args.output/'run.json').write_text(json.dumps(record,indent=2))
    status('loading')
    model=Qwen3VLForConditionalGeneration.from_pretrained(args.checkpoint,dtype=torch.bfloat16,
        local_files_only=True,attn_implementation='sdpa').to('cuda')
    model.config.use_cache=False
    selected_val=val[:args.eval_limit] if args.eval_limit else val

    def evaluate(label):
        model.eval();predictions=[]
        with torch.inference_mode():
            for row in selected_val:
                inputs={k:v.to('cuda') for k,v in encode(row,False).items()}
                generated=model.generate(**inputs,max_new_tokens=96,do_sample=False,use_cache=True)
                answer=processor.batch_decode(generated[:,inputs['input_ids'].shape[1]:],skip_special_tokens=True)[0]
                item=dict(id=row['id'],target=row['answer'],prediction=answer)
                predictions.append(item)
                print(json.dumps(dict(event='prediction',stage=label,**item)),flush=True)
                del inputs,generated
        result=dict(metrics=score_predictions(predictions),predictions=predictions)
        (args.output/f'{label}.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(dict(event='evaluation',stage=label,metrics=result['metrics'])),flush=True)
        return result['metrics']

    status('baseline_evaluation')
    baseline=evaluate('base')
    from peft import LoraConfig,get_peft_model
    config=LoraConfig(r=8,lora_alpha=16,lora_dropout=0.05,bias='none',task_type='CAUSAL_LM',
        target_modules=r'.*language_model\.layers\.\d+\.self_attn\.(q_proj|k_proj|v_proj|o_proj)$')
    model=get_peft_model(model,config)
    trainable=[(n,p) for n,p in model.named_parameters() if p.requires_grad]
    if not trainable or any('lora_' not in n or 'language_model' not in n for n,p in trainable):
        raise RuntimeError('Only language attention adapters may train')
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
    model.enable_input_require_grads()
    optimizer=torch.optim.AdamW([p for n,p in trainable],lr=5e-5,weight_decay=0.01)
    status('training',trainable_parameters=sum(p.numel() for n,p in trainable),baseline=baseline)
    order=list(range(len(train)));random.shuffle(order);cursor=0
    model.train();optimizer.zero_grad(set_to_none=True)
    for step in range(1,args.steps+1):
        begin=time.time();loss_sum=0.0
        for _ in range(args.accumulation):
            if cursor==len(order):
                random.shuffle(order);cursor=0
            row=train[order[cursor]];cursor+=1
            inputs={k:v.to('cuda') for k,v in encode(row,True).items()}
            output=model(**inputs,use_cache=False)
            if not torch.isfinite(output.loss):
                raise RuntimeError('Non-finite loss')
            loss_sum+=output.loss.item()
            (output.loss/args.accumulation).backward()
            del inputs,output
        norm=torch.nn.utils.clip_grad_norm_([p for n,p in trainable],1.0,error_if_nonfinite=True)
        optimizer.step();optimizer.zero_grad(set_to_none=True)
        event=dict(step=step,loss=loss_sum/args.accumulation,gradient_norm=float(norm),
            seconds=time.time()-begin,peak_allocated_gib=torch.cuda.max_memory_allocated()/2**30)
        print(json.dumps(dict(event='optimizer_step',**event)),flush=True)
        with (args.output/'training.jsonl').open('a') as stream:
            stream.write(json.dumps(event)+'\n')
        status('training',**event)
        if step%5==0 or step==args.steps:
            destination=args.output/f'adapter-step-{step:03d}'
            model.save_pretrained(destination,safe_serialization=True)
            processor.save_pretrained(destination)
    status('adapted_evaluation')
    adapted=evaluate('adapted')
    status('complete',adapted=adapted,adapter=str(destination),
        comparison_scope='Same-session recipe-group holdout; NOT field-test accuracy.',
        accuracy_improved_on_pilot=adapted['sequence_exact']>baseline['sequence_exact'])
    print(json.dumps(dict(event='complete',baseline=baseline,adapted=adapted)),flush=True)


if __name__=='__main__':
    main()
