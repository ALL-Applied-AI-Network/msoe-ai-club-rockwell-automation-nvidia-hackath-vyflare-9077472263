# Automatic Vial and Liquid-Surface Tracking

The experimental pixel tracker supports the active filling position in the existing fixed, unmodified 640 × 480 station view. Recorded playback and Live Mode share the same backend detector and causal association rules. It requires no per-fill box drawing or surface marking. It is not qualified for arbitrary cameras, neighboring vials, clear liquids, physical volume measurement or unattended recipe decisions.

## Requirements and Decision Rules

- Find the active vial's sustained body edges and visible rim/base from source pixels in the calibrated station search lane. Reject unsupported resolution and missing geometry rather than resize or invent a vial.
- Require two stable samples before assigning a local tracking ID. Local IDs differ from video-order vial numbers, barcodes, batch positions and recipe IDs.
- Retain the identity across an isolated exposure/motion spike only after two stable recovery samples agree with the pre-spike holder-side appearance. The holder-side comparison excludes the changing liquid and central label. Consecutive motion, absence, unresolved recovery or capture gaps greater than 0.4 seconds break association.
- Locate a broad, persistent neutral-air-to-colored-liquid boundary in unobstructed glass. Exclude the known label/holder band. Require spatial support over at least 65% of the inner width and temporal agreement across two samples. Report a dashed surface line only for supported measurements. Shading inside already colored liquid, empty glass, hidden surfaces, clear liquids and uncertain boundaries produce no line; old lines are not carried forward.
- Preserve uncertainty in the frame output and the source-linked observation summary. Box/line measurements are experimental evidence, not calibrated detection probabilities or physical volume.

Version and implementation SHA-256 are exposed with configuration. No new model weights or third-party inference service are required; pixel processing uses the installed NumPy/Pillow backend.

## Backend and Recorded Observer Integration

`GeometryService` provides bounded, five-minute-idle tracking sessions (maximum eight), strict frame dimensions, monotonically increasing capture times and a single whole-recording worker. Images in live/preview sessions are processed in memory. The whole-recording worker uses the existing local macOS native decoder at four frames per second for installed Videos 1 and 2, without reading labels during detection.

Whole-recording geometry is cached separately from recipe storage. Cache keys include source-video and implementation hashes; writes use unique temporary files followed by atomic replacement. Loaded geometry is invalidated if the source's size/modification time changes. Geometry processing and its read projections do not change the frozen producer, timing allowance, reference catalog, recipe assessments or pattern memberships.

Completed geometry joins fresh recorded-observer assessments by recording hash and each fill's original start/departure window. The supplemental summary includes tracked/visible-surface sample counts, local track IDs, explicit identity-change/visibility-gap issues and a strict continuity flag. `affects_recipe_decision` remains false. Qualification of residual tracking cases is required before adopting a geometry-based recipe eligibility policy.

## API and Frontend

Python routes under `/api/geometry`:

- `GET /status`: scope and implementation configuration.
- `POST /sessions` with `{}`: create a session.
- `POST /sessions/<id>/frame` with `image` (bounded JPEG data URL) and `captured_at`: analyze one original 640 × 480 frame.
- `DELETE /sessions/<id>`: release session memory.
- `GET` / `POST /recordings/video-1` or `video-2`: read/start a whole-recording geometry job.

The Node router forwards only these allowed paths, keeps backend credentials on the server and checks origins for mutations. The Python application's token/origin guard protects geometry routes. Whole-recording source paths and thresholds cannot be selected by request bodies.

Inspection Workspace starts pixel tracking automatically when playable media is ready. The same hook consumes recorded-video elements and live camera MediaStreams. It bounds outstanding requests, backs off on errors, releases sessions on disconnect/source change, resets after seeking and suppresses stale overlays. Source resolution is preserved. Fullscreen/letterbox overlays use normalized coordinates and the actual contained-media rectangle.

“Process Recording” starts the recorded observer and geometry sidecar together, and geometry summaries refresh when observer processing finishes. The geometry worker queues only the two allowed sources and deduplicates repeated starts. “Track Entire Recording” also produces source-linked cached geometry and per-fill diagnostics. “Review a Detected Surface” seeks to actual supporting source evidence. Recorded overlays use only a recent preceding sample and never interpolate across gaps or identities. Manual guides remain an optional advanced tool. Live visual tracking starts after camera connection; live fill completion, qualified color sampling and recipe assessment remain separate integration work.

## Validation and Limits

Development validation used complete Videos 1 and 2 (5,130 decoded samples), source-linked 22 fill windows, synthetic boundary/motion cases, two native-frame regression images, HTTP/API tests and browser playback/MediaStream checks. Counts of tracked/surface frames describe output coverage and are not accuracy estimates. The two real regression images have development-reviewed surface labels; no independent geometry ground truth exists yet.

Nineteen of 22 source fill windows have one emitted local track ID; Video 1 Vials 7 and 16 and Video 2 Vial 1 fragment. No emitted ID overlaps adjacent fill windows. These remain visible continuity issues. A strict all-samples continuity requirement is not met because even single-ID windows contain temporary unconfirmed samples.

Live Mode was exercised using an actual browser MediaStream generated from recorded Video 2, with the fixture clearly labeled and no physical camera accessed. Actual station-camera framing, transport cadence and hardware remain unvalidated. Deployment on Linux can process live/preview JPEGs; fresh whole-recording decoding retains the existing macOS dependency.

Reproduce offline measurements from the repository with:

```sh
PYTHONPATH=backend .venv/bin/python backend/scripts/smoke_geometry_tracking.py \
  --output /absolute/path/to/results \
  --observations backend/tests/fixtures/two_fill_observations.json
```

The observation file is optional and is read only after detection to join diagnostic windows. A separate demo bank is neither required nor written by this script.
