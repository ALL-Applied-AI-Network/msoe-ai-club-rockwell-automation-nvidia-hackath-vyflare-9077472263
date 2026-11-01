# Model 2 Integration

The source is `origin/Model2`, commit `e46c8e85bdaa067a10ea2392afdeab005fbc912f`.
The adapter, API, assets, fixtures and original API tests were imported selectively;
no branch merge was performed. The deployed head remains **model2-baseline-v4**
(`station-crop-v1`). The branch's v5–v7 crop/inpainting experiments do not replace it.
Its historical manifest `model_id` still says v2; `config_version` identifies the
actual deployed v4 head. Both are retained for provenance.

Install `backend/requirements-model2.txt` in a separate environment; do not install
these CPU dependencies over the Cosmos worker environment. Set
`MODEL2_BACKBONE_WEIGHTS` to a local `resnet18-f37072fd.pth` file, then add `model2`
to `ENABLED_MODELS` alongside `model4`. The adapter verifies the complete backbone
and head SHA256 hashes. Without an explicit path it uses the standard Torch cache
and downloads the pinned official ImageNet backbone when absent.

In Inspection Workspace, prepare the existing three registered 640 × 480 post-flow
frames and complete the intended comparison recipe and reliable batch context.
Select **Include Model 2 on These Same Three Frames**, then **Run Model 4 + Model 2**.
The Python `/predict/vial-evidence` endpoint decodes each frame once and runs the
two models independently under the existing shared nonblocking inference lock.
The gateway checks the returned frame/vial/batch context. Model 4-only requests
continue through their existing endpoint. `/predict/model2` also supports Model 2
alone through the gateway; see `MODEL2_API.md` for the multipart contract.

The classifier receives image features only. The intended recipe and batch position
are applied afterward to its interpretation. Scores are uncalibrated; high scores
are not verified identities or probabilities of correctness. The imported manifest
has `approved_for_supporting_evidence: false`. Results remain experimental and
cannot clear other flags, release vials, vote with Model 4, or create/update recipes.
Recipe discovery remains the separate qualified timing/color/tracking workflow.
The stored 0.90 classifier threshold is unrelated to its one-second timing tolerance.

Run the original parity/API tests with `PYTHONPATH=backend` and
`MODEL2_BACKBONE_WEIGHTS` set, using the Model 2 environment. Do not relax the
saved oracle assertions to hide runtime differences. The fixtures cover three
recorded fills, including unfamiliar/uncertain behavior; they establish integration
parity, not broad recipe-identification reliability.

Local qualification status (2026-11-01): real CPU/browser inference and 23 of the
24 imported API tests pass. One original five-decimal score-parity assertion fails
for `v5_e10` on macOS ARM64 (maximum difference 0.0002324); all three fixture top
recipes and threshold decisions are unchanged. Matching the source runtime versions
did not remove the difference. This remains an open validation issue; the original
oracle test is intentionally retained without relaxed tolerances. Full backend
suite: 381 pass, 1 failure. Frontend/gateway suite: 45 pass; production build passes.
