"""Extract ONLY existing Cosmos3-Nano reasoner tensors, strictly matching every HF key.

CPU-only streaming conversion. No Qwen model weights are downloaded or substituted.
"""
import argparse
import collections
import hashlib
import json
import shutil
from pathlib import Path


def main():
    import torch
    from safetensors import safe_open
    from safetensors.torch import save_file
    from transformers import Qwen3VLConfig, Qwen3VLForConditionalGeneration, AutoProcessor
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.out.exists():
        parser.error('Output must not already exist')
    raw=json.loads((args.source/'config.json').read_text())
    if raw.get('model_type')!='cosmos3_omni':
        parser.error('Expected the Cosmos3 omni checkpoint')
    config=Qwen3VLConfig(text_config=raw['text_config'],vision_config=raw['vision_config'],
        **{k:raw[k] for k in ['image_token_id','video_token_id','vision_start_token_id','vision_end_token_id','tie_word_embeddings','bos_token_id','eos_token_id','pad_token_id'] if k in raw})
    config.architectures=['Qwen3VLForConditionalGeneration']
    with torch.device('meta'):
        skeleton=Qwen3VLForConditionalGeneration(config)
    expected={k:tuple(v.shape) for k,v in skeleton.state_dict().items()}
    del skeleton
    index=json.loads((args.source/'model.safetensors.index.json').read_text())['weight_map']
    selected=collections.defaultdict(list)
    mapped=set()
    for key,file in index.items():
        candidate='model.visual.'+key if file.startswith('vision_encoder/') else key if key=='lm_head.weight' else 'model.language_model.'+key
        for old,new in [('self_attn.to_q.','self_attn.q_proj.'),('self_attn.to_k.','self_attn.k_proj.'),('self_attn.to_v.','self_attn.v_proj.'),('self_attn.to_out.','self_attn.o_proj.'),('self_attn.norm_q.','self_attn.q_norm.'),('self_attn.norm_k.','self_attn.k_norm.')]:
            candidate=candidate.replace(old,new)
        if candidate not in expected:
            continue
        if candidate in mapped:
            raise ValueError(f'Duplicate mapping {candidate}')
        with safe_open(str(args.source/file),framework='pt',device='cpu') as stream:
            shape=tuple(stream.get_slice(key).get_shape())
        if shape!=expected[candidate]:
            raise ValueError(f'Shape mismatch {candidate}: {shape} != {expected[candidate]}')
        selected[file].append((key,candidate));mapped.add(candidate)
    if mapped!=set(expected):
        raise ValueError(f'Missing {len(set(expected)-mapped)} reasoner tensors: {sorted(set(expected)-mapped)[:8]}')
    args.out.mkdir(parents=True)
    config.save_pretrained(args.out)
    output_index={};total=0;provenance=[]
    for number,(file,keys) in enumerate(sorted(selected.items()),1):
        output_file=f'model-{number:05d}-of-{len(selected):05d}.safetensors'
        with safe_open(str(args.source/file),framework='pt',device='cpu') as stream:
            tensors={target:stream.get_tensor(source).contiguous() for source,target in keys}
        total+=sum(t.numel()*t.element_size() for t in tensors.values())
        save_file(tensors,str(args.out/output_file),metadata={'format':'pt'})
        output_index.update({target:output_file for _,target in keys})
        provenance.append(dict(source_file=file,source_blob=(args.source/file).resolve().name,tensors=len(keys)))
        del tensors
        print(f'Wrote {output_file}: {len(keys)} tensors',flush=True)
    (args.out/'model.safetensors.index.json').write_text(json.dumps(dict(metadata=dict(total_size=total),weight_map=output_index),indent=2))
    for name in ['tokenizer.json','tokenizer_config.json','vocab.json','merges.txt','added_tokens.json','special_tokens_map.json','preprocessor_config.json','video_preprocessor_config.json','chat_template.json','chat_template.jinja']:
        if (args.source/name).is_file():
            shutil.copy2(args.source/name,args.out/name)
    AutoProcessor.from_pretrained(args.out,local_files_only=True)
    provenance=dict(source_model='nvidia/Cosmos3-Nano',source_snapshot=args.source.resolve().name,
        source_config_sha256=hashlib.sha256((args.source/'config.json').read_bytes()).hexdigest(),
        conversion='Strict one-to-one shape-checked extraction of all Qwen3-VL-shaped reasoner weights; no replacement model.',
        tensor_count=len(expected),total_bytes=total,sources=provenance)
    (args.out/'base_provenance.json').write_text(json.dumps(provenance,indent=2))
    print('STRICT EXTRACTION COMPLETE',flush=True)


if __name__=='__main__':
    main()
