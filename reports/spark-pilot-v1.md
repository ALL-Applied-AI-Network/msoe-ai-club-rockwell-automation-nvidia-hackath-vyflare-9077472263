# Spark pilot run record

This pilot adapts the Cosmos3-Nano reasoner with rank-8 LoRA on language-attention projections. The base checkpoint is preserved. It is an experiment on human-reviewed video-5 color descriptions, not a chemical identifier or a validated production inspection model.

- Spark workspace: `/home/yt-vyflare71b7/workspace/vial-finetune-20261029/`
- Original source: `nvidia/Cosmos3-Nano`, cached snapshot `e59a53c25979a090fa8706c9acc0c254a6e89b92`.
- Extraction: every expected reasoner tensor is mapped and shape checked; no substitute model weights are used.
- Data: 21 training vials, 9 validation vials; entire recipe groups 6, 9, and 13 are held out.
- Limitation: both partitions share the same recording session. The validation results cannot establish generalization to new sessions.
- Targets: human-reviewed whole-clip color sequences. Recipe colors, prior model predictions, unlinked phone photos, and unlabeled field clips are excluded.
- Runtime: PyTorch 2.10.0+cu130, Transformers 4.57.6, PEFT 0.18.1, Python 3.13.16.
- Sampling: 32 uniform video frames, total pixel budget 2,621,440 (about 320x224 per frame for these inputs).
- Optimization: BF16 base, SDPA, frozen base weights, rank 8 / alpha 16 / dropout 0.05, AdamW LR 5e-5, accumulation 4, 20 optimizer updates, seed 42.
- Checks: assistant-only loss, no trainable base/vision weights, finite loss/gradients, unchanged media hashes, recipe-group separation, and separate sequence/final-label metrics.

A one-update GPU smoke run completed successfully. Peak allocated GPU memory was 19.44 GiB; one training update took 4.09 seconds at accumulation 1. These are measurements from the smoke run, not full-run throughput estimates. Its single validation prediction did not change after that update.

The installed PyTorch build emits a GB10 compute-capability warning, but CUDA inference and an actual backward/optimizer step succeeded. No package upgrades or changes to existing Spark services were made.

The full pilot saves base and adapted predictions, per-update logs, adapter checkpoints, source/data provenance, and a final run status. See the run results for measured outcomes; no production accuracy is asserted here.

For future findings, version the corrected/expanded labels and start another adapter from the unchanged base. Keep old adapters for comparison and rollback. Continuing an adapter is possible but is not implemented in this pilot runner; corrections to bad labels usually warrant a fresh comparison from the base. Independent real-session evaluation remains required before deployment.

## Measured result

| Metric | Base | Adapter, step 20 |
|---|---:|---:|
| Valid JSON | 7/9 | 9/9 |
| Exact color sequence | 0/9 | 4/9 |
| Exact final color label | 3/9 | 5/9 |

The run completed successfully in 8.1 minutes including loading and both evaluations. The 20 optimizer updates took 4.5 minutes excluding checkpoint saves. Peak allocated GPU memory was 19.54 GiB. There were 7,667,712 trainable adapter parameters.

Sequence agreement improved from 0% to 44.4%, and final-label agreement from 33.3% to 55.6%, on nine within-session development clips. These numbers are NOT production accuracy or an independent-session evaluation. They are not directly comparable to the older workbook-wide 12/30 description agreement, which used different prompts/inputs and a different sample set.

All three held-out blue-to-dark-green sequences were reduced to green. Vial 26 lost its orange-to-brown transition. Vial 5 gained an extra yellow stage. The result therefore demonstrates better format compliance and some label agreement, with important temporal/shade errors remaining. Coarse whole-clip labels can also penalize plausible short stages that reviewers did not annotate. No model was deployed or substituted into the existing backend.

| Vial | Human target sequence | Adapted sequence |
|---|---|---|
| video5-vial-04 | green | green |
| video5-vial-05 | orange | yellow → orange |
| video5-vial-06 | orange | orange |
| video5-vial-13 | blue → dark green | green |
| video5-vial-14 | blue → dark green | green |
| video5-vial-15 | blue → dark green | green |
| video5-vial-25 | orange | orange |
| video5-vial-26 | orange → brown | orange |
| video5-vial-27 | orange | orange |

Adapter artifact: `outputs/spark-pilot-v1/adapter-step-020/adapter_model.safetensors` (ignored by Git). SHA-256: `9dae56b981de7e7de200e39580e57cbcba81d3efdcf940f2e025e80a41a3a5f4`. All 288 saved adapter tensors were checked for finite values, adapter-only names, expected shapes, and total parameter count. The trainer source hash matches the run record.
