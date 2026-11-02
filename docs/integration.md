# Vyflare Integration Guide

The maintained startup, workflow, storage, validation and deployment overview is
in the [root README](../README.md). This file previously duplicated the initial
image-analysis integration instructions and is now an index to avoid conflicting
startup guidance.

- [Automatic recorded inspection and playback log](../backend/recipes/automatic_recordings.md)
- [Recorded producer, current contract and development history](../backend/recipes/recorded_producer.md)
- [Tracking-gated recipe eligibility](../backend/recipes/recorded_workflow_integration.md)
- [Geometry tracking and qualification](../backend/recipes/geometry_tracking.md)
- [Cosmos and DGX integration](../backend/COSMOS_INTEGRATION.md)
- [Model 4 API](../backend/MODEL4_API.md)
- [Model 2 integration and open qualification issue](../backend/MODEL2_INTEGRATION.md)
- [Recorded data-pipeline diagram](architecture/README.md)

Automatic recipe processing starts on first playback, uses a separately configured
experimental bank and continues while paused. The Inspection Log follows playback
time. Model APIs remain separate from automatic recipe decisions. Fresh recorded
processing currently requires macOS native decoding; Node/Render hosting alone
does not enable it. Live recipe processing remains deferred.
