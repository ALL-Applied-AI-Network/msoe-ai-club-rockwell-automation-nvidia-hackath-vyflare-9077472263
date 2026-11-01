# DGX worker and laptop startup

**Native Framework worker guide.** For the latest `codex/cosmos3-nano-finetune` Version 1 LoRA worker on port 7865, use [the current console integration guide](../COSMOS_INTEGRATION.md). The native worker below remains a separate optional configuration.

The gateway runs ResNet-18 on the laptop CPU and sends `cosmos_full` requests
through SSH to Cosmos3-Nano on the DGX GB10. Full is the remote route name;
it currently uses the cached Nano checkpoint, not a separate larger model.

## DGX worker

Deployed folder:
`/home/yt-vyflare71b7/workspace/vial-baseline/cosmos-api-worker`

Its `.env` contains:

```dotenv
PORT=8001
MODEL_MODE=real
ENABLED_MODELS=cosmos
COSMOS_CHECKPOINT=Cosmos3-Nano
COSMOS_MAX_NEW_TOKENS=128
```

The launcher uses the existing Framework environment and HF cache. The worker
was started in the background, independently of an interactive SSH session.
It is not configured to restart automatically after a machine restart.

Connect with `ssh yt-vyflare71b7@172.30.102.122`, then check:

```bash
curl http://127.0.0.1:8001/health
tail -n 30 /home/yt-vyflare71b7/workspace/vial-baseline/cosmos-api-worker/worker.log
```

If health fails and the worker is no longer running, start it in the foreground:

```bash
bash /home/yt-vyflare71b7/workspace/vial-baseline/cosmos-api-worker/dgx/start-worker.sh
```

Keep that terminal open for a foreground worker. Do not start another worker
if health already succeeds; each instance would load its own model weights.
The API becomes ready only after model initialization. Press Ctrl+C to stop
a foreground worker. GPU memory remains allocated while the worker is running.

## Laptop

From the project folder, use three separate PowerShell terminals and leave
them open. Keep the laptop `.env` set to `MODEL_MODE=real`,
`ENABLED_MODELS=resnet18,cosmos_full`, and `RESNET_DEVICE=cpu`.

1. SSH tunnel:

   ```powershell
   ssh -N -o ExitOnForwardFailure=yes -L 8001:127.0.0.1:8001 yt-vyflare71b7@172.30.102.122
   ```

2. Local backend:

   ```powershell
   cd backend
   .\.venv\Scripts\python.exe app.py
   ```

3. Frontend:

   ```powershell
   cd backend
   .\.venv\Scripts\python.exe -m http.server 3000 --bind 127.0.0.1 --directory frontend
   ```

Open http://127.0.0.1:8001/health to check the DGX through the tunnel. It must
report real mode and model `cosmos`. Then open http://localhost:3000, refresh
with Ctrl+F5, and select **ResNet-18 + Cosmos Full (DGX Spark)**. Both results
appear under `results`. Cosmos execution metadata identifies Linux/aarch64,
hostname `vyflare71b7`, and GPU `NVIDIA GB10`.

## Validation and limitations

On October 26, 2026, a real synthetic vial image returned HTTP 200 and
`A blue liquid in a glass container.` from the worker in about 16 seconds.
This verifies execution and transport, not industrial inspection accuracy.

This installed Framework release disables image content classification. The
API reports `input_image: disabled_in_framework_release`; face postprocessing
and prompt/output text checks remain active. Classifier exceptions in the
adapter propagate as errors. Local ResNet still uses general ImageNet weights.

The shared Spark dashboard is https://www.yaadops.com/. The worker uses the
existing team SSH workspace. Follow any team scheduling requirements for
continued GPU use. The service is loopback-only; no public port was opened.
