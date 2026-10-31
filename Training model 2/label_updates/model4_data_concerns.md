# Further data concerns for Model 4's training vials

Found during the Model 2 baseline (`Training model 2/model2_baseline/`). Model 4 is
unchanged. The integration owner should review these before retraining or relabeling.
Label changes are listed separately in `README.md` and the CSVs in this folder.

## Recording with conflicting metadata

`data/60/60-video.json` (recording `20261028_205922_757261`, the workbook's recipe 60
vials `field_v11–15`) records `notes: "rec #99"` and 50 mL water, not recipe 60. The
recording is quarantined for Model 2 until an operator confirms it. **Model 4 trained on
`field_v12–v15`** from this recording.

## Flow still visible at early post-flow times

Model 2 checked frames at `end_s` + 0.05/0.15/0.25 s, using workbook `end_s`, for a
liquid stream in the Model 4 stream ROI (`outputs/frames_manifest.csv` in the
baseline folder). Model 4 selects frames from its own reviewed no-flow bracket and
Video 5 offset, so whether its frames are affected still needs checking against its
own timestamps.

| Vial | Frames with visible stream | In Model 4 training |
|---|---|---|
| `field_v23`, `v24`, `v25` (recipe 50, unlabeled) | all three | yes |
| `field_v10` (99) | all three (thin, clear) | yes |
| `field_v09` (99) | +0.05, +0.15 | yes |
| `field_v01`, `v21`, `v22` | all three | no |
| `v5_e12`, `e14`, `e24`, `e27` | +0.05 | yes |
| `v5_e23` | +0.05, +0.15 | yes |
| `v5_e13`, `e16`, `e22` | +0.05 | no |

For `field_v01` and `v21–25` the workbook `end_s` falls before the end of flow.
