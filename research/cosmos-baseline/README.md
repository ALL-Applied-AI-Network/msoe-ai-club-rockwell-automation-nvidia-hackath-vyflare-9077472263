# Cosmos vial-event input packages

30 events cut from vial_fill_video_5.mp4 using the precise start_s/end_s columns in video5_vial_recipes.csv. Original video and label files were not changed.

Folder names use f26-rnh-vf-MMmSSsmmm-MMmSSsmmm (minutes, seconds, milliseconds). Example: f26-rnh-vf-02m18s250-02m41s318.

Each folder contains:
- input/clip.mp4: H.264 clip, original 640x480 resolution and 30 FPS, re-encoded at CRF 18 for accurate cuts, no audio.
- input/recipe.labels.json: recipe metadata plus all matching frame-label rows and image references. Frame timestamps are also expressed relative to the clip. Referenced source images are not duplicated.
- input/observation-prompt.json: the human-readable prompt record.
- input/oberservation.json: executable Cosmos input, with the prompt embedded and video_fps=2.0.
- input/run-oberservation.sh: inference launcher for the configured Linux/NVIDIA environment.
- output/: empty until inference runs; each run creates a new timestamped subfolder.

The spellings oberservation.json and run-oberservation.sh match the requested filenames. Future results use observation-parsed.json.

## Labels and unbiased observation
Recipe metadata is kept separate from the VLM prompt. color_purpose describes intended appearance, not independently verified visual ground truth. Blank source cells are retained in source_recipe_row and represented as null in typed metadata. Recipes 11–14 have no color_purpose. Neither recipe identity nor mismatch correctness is inferred from these labels alone. Negative and between-fill image timestamps outside the event intervals are excluded. Source frame indices are retained for traceability, but second-based timestamps control cutting.

observation-prompt.json is a reference copy; to edit the prompt used in a run, update the prompt field in oberservation.json too. The launcher reads oberservation.json.

## Run on Spark after transferring a complete clip folder
Activate or point to the existing Cosmos installation, then:

```bash
export COSMOS_REPO=/workspace/vial-baseline/cosmos-framework
bash /path/to/f26-rnh-vf-02m18s250-02m41s318/input/run-oberservation.sh
```

The script reuses /workspace/hf/hub if available and preserves the existing authentication configuration. CUDA 13 NPP preload fix is included. To select another checkpoint, set COSMOS_CHECKPOINT. OUTPUT_DIR may override the output destination.

Raw model text, logs and settings are preserved. Valid JSON responses get an observation-parsed.json copy; invalid JSON is recorded in json-validation.json. Recipe labels are copied to results for review but are not submitted to the model.

## Validation
manifest.json lists every clip, source boundaries, duration, matching image-label count, size and SHA-256. All clips were fully decoded, timings checked within 0.07 seconds (video frame granularity), all JSON files parsed, and all shell scripts syntax-checked. No model runs were launched during packaging. Semantic annotation accuracy has not been verified.
