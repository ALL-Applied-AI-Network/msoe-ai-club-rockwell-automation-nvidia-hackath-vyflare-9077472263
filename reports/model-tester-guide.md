# Using the Spark model tester

The browser interface loads the extracted Cosmos3-Nano reasoner and saved pilot adapter. Switching the adapter off gives the base comparison without loading another full model.

## Open the tester

1. Connect your computer to the network or VPN that reaches the Spark.
2. Open **http://172.30.102.122:7865/** in your browser.
3. Upload a short vial video, preferably under one minute and containing the vial under the nozzle. MP4, MOV, AVI, and MKV are accepted, up to 100 MiB. A long clip is allowed up to ten minutes but still uses only 32 uniform samples, so short events may be missed.
4. Choose **Compare base and fine-tuned**, **Fine-tuned only**, or **Base only**, then click **Run test**.
5. Inspect raw text, parsed color JSON, and validity for each requested model. Compare with the video rather than assuming a well-formatted answer is correct.
6. Click **Download result JSON** to keep a result. To contribute a correction, enter your observed sequence (for example `blue > dark green`) and/or notes, then click **Save human feedback**. Download again to include the feedback.

JPEG, PNG, and WebP photos are also accepted. Photo mode asks for a single visible color without inferring history. It is exploratory: the pilot adapter was trained on videos, not these photos. The phone/station view difference remains a limitation.

Uploaded media is deleted after inference; it is not archived. Only an explicit feedback submission stores a result with the file name/hash, predictions, reviewer fields, and correction under the Spark's `tester-feedback/` directory. Corrections are marked as submitted for review, not automatically accepted ground truth, and do not retrain the model. Keep the original clip yourself if you want to use it for future training. The last 100 results are temporarily available for feedback in the running service; download results you need to retain.

## Other testers

Share the private URL above with teammates who already have a network/VPN route to the Spark. They need a browser, not Python, model downloads, or an NVIDIA GPU. VPN access and network policy may differ by user. This is a private-network tester with no public tunnel or application login; share it only within that intended group.

The service allows one model request at a time. A second request gets a busy response and should be retried after the first test finishes. Compare mode runs the two predictions sequentially. No other Spark workloads are stopped.

If the direct URL does not work but SSH does, use a local tunnel:

```powershell
ssh -N -L 7865:127.0.0.1:7865 yt-vyflare71b7@172.30.102.122
```

Leave that terminal open and browse to **http://127.0.0.1:7865/**. Teammates should use their own authorized SSH accounts if they need a tunnel. Do not share passwords or private keys.

## Service lifecycle on the Spark

Workspace: `/home/yt-vyflare71b7/workspace/vial-finetune-20261029/`

Health: `http://172.30.102.122:7865/health`

Log: `tester.log`. PID record: `tester.pid`.

The process is started with `nohup`, so closing SSH does not stop it. It is not configured to restart after a Spark reboot. It keeps a model resident in memory while running.

To start it again, first verify that the existing tester is not already running on port 7865. Then, from the workspace:

```bash
nohup /home/yt-vyflare71b7/workspace/vial-baseline/cosmos-framework/.venv/bin/python -u scripts/serve_spark_adapter.py \
  --checkpoint base-reasoner \
  --adapter runs/pilot-v1/adapter-step-020 \
  --host 0.0.0.0 --port 7865 --feedback-dir tester-feedback \
  > tester.log 2>&1 < /dev/null &
echo $! > tester.pid
```

Wait for `Model ready; serving` in the log before opening the page. Model loading can take a few minutes.

## Interpreting results

This is the pilot with 4/9 sequence agreement and 5/9 final-label agreement on a same-session development partition. It is not an independently validated inspection system. Color descriptions do not establish chemical identity, exact volume, or contamination. Collect results on new real sessions and review them before claiming deployment accuracy.

The tester uses the same video question, 32-frame sampling, greedy decoding, and 96-token output budget as the pilot evaluation. It does not yet crop or track the vial automatically. Photos use a separate single-image prompt. Result JSON records the prompt, source snapshot, adapter, and sampling information.

## Verification performed

The service was started and reached from the project computer through the VPN at the direct URL. A real held-out video comparison reproduced the pilot outputs: base `clear > green`, adapter `green`; request processing took approximately 8.8 seconds. The saved adapter therefore loaded successfully in a separate inference process. The exploratory photo path was also exercised. These are interface smoke tests, not new accuracy measurements.

Six serving API tests passed in the Spark environment: page/health, temporary-upload cleanup, explicit feedback persistence, invalid requests, upload-size rejection, and concurrent-request rejection. The served browser JavaScript passed a syntax check. Full multi-user browser interaction has not been independently exercised.
