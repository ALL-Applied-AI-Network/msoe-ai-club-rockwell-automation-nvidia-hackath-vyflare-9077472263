# Visual-quality label updates affecting Model 4

Source: `Training model 2/recipes.xlsx`
SHA-256 `771c86eada3de6f9b430d3a03c622468375c088871b855a59b98724ae1be6aea`
(revised three times on 2026-10-31; earlier `f98b3a74…cce2`, `336b6c09…0a05` and
`1160090945b6…121a`, see "Workbook revisions" below),
sheets `Recipes_5_to_14` and `Recipes_41_50_60_99`, column with header `bad or good`.
This is the workbook selected for Model 2. It differs from the workbook recorded
in `backend/model4_assets/recipes.json` (`e95239f5…3b57`, sheet `Recipe_Bank`,
nominal recipe settings only). `Recipe_Bank` contains no visual labels.

"Previous label" is how the frozen Model 4 checkpoint
(`backend/model4_assets/checkpoint.json`) treated each vial: membership in
`training_vials`, or exclusion by `first_after_change_policy`. No earlier workbook
version with visual labels exists in Git.

Regenerate with `python "Training model 2/label_updates/build_label_updates.py"`.

## Affected vials (`model4_affected_vials.csv`)

| Model 4 key | Sheet | Recipe | Vial | Batch position | Batch preceded by | Previous | New |
|---|---|---|---|---|---|---|---|
| v5_e01 | Recipes_5_to_14 | 5 | 1 | 1 | unknown | excluded as first vial, not a defect label | bad |
| v5_e04 | Recipes_5_to_14 | 6 | 4 | 1 | 5 | excluded as first vial, not a defect label | bad |
| v5_e07 | Recipes_5_to_14 | 7 | 7 | 1 | 6 | excluded as first vial, not a defect label | bad |
| v5_e10 | Recipes_5_to_14 | 8 | 10 | 1 | 7 | excluded as first vial, not a defect label | bad |
| v5_e13 | Recipes_5_to_14 | 9 | 13 | 1 | 8 | excluded as first vial, not a defect label | bad |
| v5_e16 | Recipes_5_to_14 | 10 | 16 | 1 | 9 | excluded as first vial, not a defect label | bad |
| v5_e19 | Recipes_5_to_14 | 11 | 19 | 1 | 10 | excluded as first vial, not a defect label | bad |
| v5_e22 | Recipes_5_to_14 | 12 | 22 | 1 | 11 | excluded as first vial, not a defect label | bad |
| v5_e25 | Recipes_5_to_14 | 13 | 25 | 1 | 12 | excluded as first vial, not a defect label | bad |
| v5_e28 | Recipes_5_to_14 | 14 | 28 | 1 | 13 | excluded as first vial, not a defect label | bad |
| field_v17 | Recipes_41_50_60_99 | 99 | 17 | 2 | 60 | **in Model 4 training fit** | bad |
| field_v22 | Recipes_41_50_60_99 | 50 | 22 | 2 | 99 | **in Model 4 training fit** | bad |
| field_v27 | Recipes_41_50_60_99 | 99 | 27 | 2 | 50 | **in Model 4 training fit** | bad |
| field_v28 | Recipes_41_50_60_99 | 99 | 28 | 3 | 50 | **in Model 4 training fit** | bad |

The list holds every bad first vial in `Recipes_5_to_14` and every bad later vial in
`Recipes_41_50_60_99`.

Impact:

- The ten `Recipes_5_to_14` first vials were already outside the Model 4 fit, so
  the fit is unchanged. Their status changes from a process rule to an explicit
  human visual label. The first-vial contamination flag stays independent of it.
- `field_v17`, `field_v22`, `field_v27` and `field_v28` are later vials labeled bad. Bad vials
  are therefore not limited to first vials. Model 4 trained on all four as acceptable recipe
  examples, so published Model 4 metrics used the earlier eligibility rule and
  are not an evaluation against these labels.

## Related vials for review (`model4_related_vials.csv`)

Not part of the requested change list, recorded so the integration owner sees them:

- `field_v01`, `v06`, `v11`, `v16`, `v21`: first vials labeled bad; already
  excluded from the Model 4 fit.
- `field_v26`: first vial (recipe 99 after 50) now labeled **good**. It stays outside
  the Model 4 fit, and its first-vial contamination flag still applies regardless of the label.

## Workbook revisions (2026-10-31)

`1160090945b6…121a` → `336b6c09…0a05`: column S of `Recipes_41_50_60_99`, rows 24–31,
previously blank:

| Vial | Recipe | Batch position | New label | Model 4 fit |
|---|---|---|---|---|
| 23, 24, 25 | 50 | 3, 4, 5 | good | trained on; now confirmed good |
| 26 | 99 (after 50) | 1 | bad | excluded as first vial |
| 27, 28, 29, 30 | 99 (after 50) | 2–5 | good | trained on; now confirmed good |

`336b6c09…0a05` → `f98b3a74…cce2`: vial 27 (row 28) good → **bad**. This matches the
operator's description of its photo (`99/50-flush/99-2.jpg`, deep orange).

`f98b3a74…cce2` → `771c86ea…6aea`: vial 26 (row 27) bad → **good**; vial 28 (row 29)
good → **bad**. Vial 27 (row 28) stays bad. Each sheet row number is the vial number plus one.

No timing cells changed in any revision.

## Not done here

Model 4's checkpoint, assets and code are unchanged. Retraining or relabeling
Model 4 is left to the integration owner.
