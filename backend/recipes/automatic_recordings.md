# Automatic Recorded Inspection and Playback Log

The recorded inspection page starts analysis when a supported recording first
plays. The manual mixture-comparison form, reviewed timeline and separate
Process Recording panel have been removed from this page. Cosmos prompting
remains a separate optional tool. Live recipe completion is still deferred.

## Data Flow

1. Installed Videos 1–5 can be selected. Open a Recording sends new MP4/MOV/WebM
   media to the private Python gateway without manual source registration.
2. Uploads are bounded to 128 MiB per recording and 512 MiB total storage. Files
   are stored under generated SHA256 identities, never client-supplied paths.
   Exact copies of installed footage reuse its identity. Reopening/replaying
   unchanged media reuses its existing job/log and does not add recipe votes.
3. On first play the browser POSTs an empty object to the idempotent
   `/api/recorded-observer/videos/{id}/ensure` route. One background worker
   processes recordings, with at most four active/queued jobs. Switching sources
   disconnects their browser polls, not their background analysis.
4. The native decoder reads actual media. The existing observer, timing refinement,
   color sampling, tracking gate, one-second matching allowance, color-conflict
   flags, pending groups and provisional recipe decisions remain in force. No
   reference annotation, expected recipe, training or per-recording tuning is an
   observation input. Producer provenance is now `fixed-station-native/4`.
5. Each completed fill contributes source-timestamped flow, duration, gap, RGB
   appearance and recipe-outcome entries. Recipe outcomes wait for final sampling
   and departure evidence. Pattern-membership changes are captured after each
   chronological assessment, so a later confirming fill cannot reveal its ID in
   an earlier log entry. Existing historical banks without log journals use the
   original saved decisions, not memberships projected from future observations.
6. Log visibility follows video time. Pause freezes incoming entries even when
   backend analysis finishes; resume admits only entries at/before the current
   time. Seeking explicitly synchronizes the history to the new time and hides
   future entries. Analysis can lag playback; the UI reports progress/catching up
   rather than filling the log with reviewed labels.

## Storage and Deployment

`RECORDING_UPLOAD_ROOT` optionally selects the recording/log directory; by default
it is a `recordings` directory beside the separate `RECIPE_DEMO_DB_PATH`. Its
content-addressed logs survive a backend restart on persistent storage. The
normal bank remains separate. Existing source profiles and engine-1.4 membership
history are preserved; no reference/threshold changes or automatic migrations.

New recording uploads through the Node proxy currently require a loopback client
and loopback hostname. This supports the requested local workflow without adding
anonymous public media uploads. The Render team must establish authenticated
upload access before enabling that capability remotely. Existing installed-video
routes remain available through the current proxy.

Fresh acquisition still requires macOS, AVFoundation and `swiftc`, the calibrated
640 × 480 original station view, no rotation, and a recording of at most 30
minutes. Browser playback support does not establish decoder/geometry support;
unsupported recordings return explicit errors, not recipe decisions. Linux
requires a separately validated decoder. Model 2 is optional and does not take
part in recipe decisions; Cosmos/Model 4 calls are not required by the existing
pixel observer/matcher.

## APIs

Private Python (`INFERENCE_TOKEN` protected):

- `POST /api/recipe-workflow/demo/producer/recordings`: raw video body with a
  supported Content-Type and optional URL-encoded `X-Recording-Name` header.
  Returns a content-addressed `video_id` and SHA256.
- `POST /api/recipe-workflow/demo/producer/videos/{id}/ensure`: empty JSON;
  returns an existing result/job or queues fresh analysis.
- `GET /api/recipe-workflow/demo/producer/videos/{id}`: progress, source hash,
  assessments, evidence-timed events and analyzed-through timestamp.

Node exposes the same producer operations under `/api/recorded-observer`.
IDs are installed `video-1` through `video-5`, or `recording-` plus 64 lowercase
hexadecimal SHA256 characters. File names/paths/measurements are not job inputs.
The prior explicit POST-to-video processing route remains available for controlled
retry/reprocessing, but is not the primary inspection UI.
