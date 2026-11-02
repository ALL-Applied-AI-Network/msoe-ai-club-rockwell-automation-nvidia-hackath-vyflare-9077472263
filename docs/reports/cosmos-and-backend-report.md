# VyFlare: Cosmos Observation and Inference Integration Report

**Date:** October 26, 2026  
**Repository branch reviewed:** `cosmos_switch_function`  
**Reviewed commit:** `a418435` — “Made Changes To Use DGX Spark. (Functional, but in progress)”

## 1. Introduction

We are developing an AI-assisted monitoring workflow for an automated vial-filling station. The goal is to turn visual observations into information an operator can use, including descriptions of liquid appearance and, eventually, classifications displayed alongside camera imagery for potential error checking.

Work has progressed along two complementary tracks: testing pretrained Cosmos3-Nano on recorded vial-filling clips, and building a backend that connects a browser client to local classification and remote Cosmos inference. This report covers the retained baseline tests and the implementation on the `cosmos_switch_function` branch.

## 2. Methodologies, Tools, and Infrastructure

### Video Preparation and Baseline Methodology

The source recording, `vial_fill_video_5.mp4`, was divided into 30 clips using the start and end timestamps in `video5_vial_recipes.csv`. These clips cover vials 1–30 and recipes 5–14. Associated frame labels and recipe information were retained for reference.

Each clip was organized under `cosmos-model-data` using the naming pattern `f26-rnh-vf-<start-time>-<end-time>`. An `input` folder contains the video, recipe labels, observation prompt, inference configuration, and execution script; an `output` folder stores results.

FFmpeg produced H.264 clips at the source resolution of 640 × 480 and 30 frames per second. Cosmos sampled the footage at two frames per second. Video decoding, duration, file hashes, JSON inputs, and execution scripts were checked during preparation.

The baseline prompt asked Cosmos to identify the target vial, describe visible filling activity, distinguish nozzle-stream color from liquid color in the vial, describe color changes, and acknowledge limitations. Recipe information was withheld from the model prompt to avoid supplying expected answers. Raw responses were retained, and Markdown wrappers were removed where needed to create parsed JSON files.

### Infrastructure and Tools

| Component | Role |
|---|---|
| MacBook Pro with M4 Pro | Preparing clips, managing project files, reviewing observations, and developing the client/backend |
| YAAD Vyflare workspace on DGX Spark | Remote Linux/NVIDIA GB10 compute for Cosmos |
| SSH and file transfer | Accessing the workspace and moving test inputs/results |
| NVIDIA Cosmos Framework and PyTorch | Loading Cosmos3-Nano and executing inference |
| Cosmos guardrail components | Content-related text checks and framework-supported image processing |
| Python, FFmpeg, and JSON | Data preparation, validation, and result handling |
| Flask and Waitress | Backend API |
| HTML and JavaScript | Browser-based API test client |
| Torchvision ResNet-18 | Local image-classification baseline and support for custom classification weights |
| Git and Python unittest | Version tracking and automated backend verification |

The recorded-video baseline used a batch process: the model loaded once, processed 30 clips sequentially, and exited. The repository integration introduces a separate persistent worker that keeps Cosmos available for image requests.

### Work on `cosmos_switch_function`

The branch builds on the backend inherited from `implement-backend`. Two branch commits introduce model routing and then adapt it for the DGX Spark. The reviewed working tree was clean and matched its locally recorded remote-tracking branch.

The main additions are:

- **Per-request model selection.** `cosmos_lite` uses the existing local Cosmos adapter; `cosmos_full` forwards requests to the Spark worker. Selection is specific to each request rather than a global setting shared by clients.
- **Paired inference.** The frontend can request ResNet-18 and the selected Cosmos route for the same image. The backend runs them sequentially and returns both outputs. A failure produces an error rather than partial paired results.
- **Remote worker integration.** The gateway forwards images and prompts to the worker through HTTP over an SSH tunnel. Returned execution metadata identifies the worker platform and GPU.
- **Explicit error handling.** Busy workers, safety rejections, connection failures, timeouts, and invalid responses receive distinct error responses. Remote failures do not silently fall back to local inference or mock results.
- **Runtime compatibility fixes.** The branch preserves the API’s image-size limit even when the framework changes Pillow settings, and propagates text-classifier failures rather than treating them as safe results.
- **Deployment documentation.** A worker launcher and startup guide describe the Spark environment, gateway, SSH tunnel, and browser client.

“Lite” and “Full” currently describe execution routes. Both use Cosmos3-Nano; “Full” does not indicate a separately deployed larger model. Local Cosmos execution still needs a compatible Linux/CUDA environment, so the practical laptop configuration uses local CPU ResNet and remote Cosmos.

The documented topology is:

**Browser client (port 3000) → local gateway (port 8000) → local ResNet / SSH tunnel → Spark Cosmos worker (port 8001).**

The branch’s “switch” refers to selecting an inference route.

## 3. Results

### Video results

All 30 clips completed Cosmos inference successfully. All 30 responses parsed as JSON after wrapper removal and passed the baseline field/type checks. Results are preserved in each clip’s `output/20261025-batch01/` directory.

The batch took approximately 24 minutes, with individual observations generally taking around 40–60 seconds. Reported liquid appearances included green, blue, orange, yellow, and brown, with some clips describing changes over time.

### Human Verification of Baseline Observations

We reviewed all 30 baseline outputs and recorded judgments in [the verification workbook](../../research/cosmos-baseline/output-verification.xlsx). All vial numbers and clip-folder identifiers match the dataset manifest. The workbook was read without modification.

The explicit `correct` column (`D3:D32`) marks **24 of 30 color descriptions correct (80.0%)** and **6 of 30 requiring correction (20.0%)**. There are no blank correctness ratings. These figures measure agreement with one reviewer on this recorded batch; they are not a held-out generalization score or an accuracy measure for every field in the model responses. The separate 30/30 JSON validation result measures structure only.

| Vial | Original color description recorded in workbook | Reviewer correction | Interpretation of correction |
|---|---|---|---|
| 17 | yellow | yellow to green | Missed yellow-to-green transition |
| 18 | yellow | yellow to green | Missed yellow-to-green transition |
| 22 | green | blue to green | Missed initial blue color / transition |
| 26 | dark brown to light brown | brown | Reported shade transition not confirmed by reviewer |
| 29 | green | light green | Missing light-green shade qualifier |
| 30 | green | light green | Missing light-green shade qualifier |

The original model outputs remain unchanged. The six review exceptions comprise three missed color transitions, one unconfirmed shade transition, and two shade-description corrections. These categories summarize the review notes rather than adding new visual judgments.

The workbook also records `yes` for filling descriptions and color-change descriptions on all 30 vials, `na` for neighbors, and `none` for anomalies (meaning no anamolies detected). These were noted whether the cosmos model metions these cases in the output, therefore the `yes` entries are reported as description checks, not 100% correctness. Neighbor handling is not assessed, and the absence of noted anomalies does not measure anomaly-detection sensitivity.

### Backend and Routing Verification

During preparation of this report, the branch’s automated suite was rerun: **26 tests passed**. Coverage includes image and request validation, model routing, paired inference, busy handling, recovery after failures, rejection of mock or incompatible remote responses, and text-safety error behavior.

These tests use mocks and controlled local HTTP endpoints. They validate application behavior; they do not measure real-model accuracy or GPU performance.

The DGX deployment guide separately records a real worker test on October 26: a synthetic vial image returned HTTP 200 with the description **“A blue liquid in a glass container.”** in approximately 16 seconds. This is documented evidence of successful model execution and transport, not an industrial-inspection benchmark. The live worker’s current availability was not rechecked for this report.

### Findings and Limitations

1. **The baseline observation pipeline works end to end, with measured review exceptions.** All 30 clips returned structurally valid results; human review accepted 24 color descriptions and corrected six. The main issues were transitions and shade detail.
2. **The branch extends batch experimentation toward application integration.** A persistent worker avoids loading Cosmos anew for every API request.
3. **The API currently accepts individual images.** A frame response cannot establish motion or the sequence of events across a video. The clip-based results and image-service result are different workloads and should not be treated as directly comparable latency measurements.
4. **ResNet remains a general baseline.** Its default ImageNet weights do not establish vial-color, recipe, or defect classification accuracy. The adapter supports custom weights and ordered labels, but the reviewed evidence does not demonstrate a validated vial-specific classifier.
5. **Content-safety capability is reported explicitly.** The documented installed framework disables image content classification. The API reports this limitation; text checks and image postprocessing remain active. Content checks do not establish industrial correctness.
6. **Concurrency is intentionally limited.** One inference gate serializes work, and the client skips requests while busy. Slow Cosmos requests can delay local classification updates.
7. **The interface and service are demonstration infrastructure.** The frontend is an API test client, and the documented worker does not automatically restart after a machine reboot. No final live-monitoring UI or production availability guarantee has been established.

No Cosmos fine-tuning was performed in the work covered by this report.

## 4. Conclusion

The project has demonstrated pretrained Cosmos observations on 30 vial-filling clips and implemented a backend path connecting a browser client, local ResNet classification, and remote Cosmos inference on the DGX Spark.

The strongest evidence is the successful 30-clip baseline, 24 of 30 color descriptions accepted in the project owner’s recorded review (80.0% agreement), the documented real image request on the Spark, and the 26 passing backend tests. Six color descriptions need correction, mainly for transitions or shade detail. This provides a measured baseline for this batch; broader accuracy and operating performance still require evaluation on separate recordings.

Next steps are to use the six reviewed corrections as regression cases while retaining the 24 accepted examples, assess improvements on separate recordings, measure the paired request path under realistic use, and connect validated outputs to the operator interface. The reviewed batch should not be presented as an unseen test set after it is used to guide changes. A vial-specific classifier should be assessed separately before its labels are used for inspection decisions.

## Evidence reviewed

- [Baseline result summary](../../research/cosmos-baseline/README.md)
- [Human verification workbook](../../research/cosmos-baseline/output-verification.xlsx)
- [Backend architecture and API documentation](../../backend/README.md)
- [Spark deployment and documented live test](../../backend/dgx/README.md)
- [Model adapters and remote routing](../../backend/models.py)
- [API tests](../../backend/tests/test_api.py) and [routing tests](../../backend/tests/test_cosmos_switch.py)
- Branch changes: `1b5469e` and `a418435`, compared with `implement-backend` at `b9184d9`.
