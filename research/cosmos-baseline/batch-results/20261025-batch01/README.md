# Cosmos clip test — 2026-10-25

Clips: 30. Valid JSON: 30. Valid schema: 30.

Pretrained inference only. Recipe labels were withheld from the prompts. Format checks do not measure visual accuracy.

| Vial | Recipe | JSON / schema | Observed liquid color |
|---|---|---|---|
| 1 | 5 | True / True | Green |
| 2 | 5 | True / True | Green |
| 3 | 5 | True / True | Green |
| 4 | 6 | True / True | Dark green |
| 5 | 6 | True / True | Orange |
| 6 | 6 | True / True | Orange |
| 7 | 7 | True / True | The liquid inside the vial starts as orange and transitions to green. |
| 8 | 7 | True / True | Blue |
| 9 | 7 | True / True | Blue |
| 10 | 8 | True / True | Blue, then green |
| 11 | 8 | True / True | green |
| 12 | 8 | True / True | Green |
| 13 | 9 | True / True | Green |
| 14 | 9 | True / True | Green |
| 15 | 9 | True / True | Dark green |
| 16 | 10 | True / True | Green |
| 17 | 10 | True / True | Yellow |
| 18 | 10 | True / True | Yellow |
| 19 | 11 | True / True | Green |
| 20 | 11 | True / True | Blue |
| 21 | 11 | True / True | Blue |
| 22 | 12 | True / True | Green |
| 23 | 12 | True / True | Brown |
| 24 | 12 | True / True | Orange |
| 25 | 13 | True / True | Brown |
| 26 | 13 | True / True | Dark brown, then lighter brown |
| 27 | 13 | True / True | Dark brown |
| 28 | 14 | True / True | Orange initially, darkening to brown as the vial fills |
| 29 | 14 | True / True | Green |
| 30 | 14 | True / True | Green |

## Visual review needed

Some clips with the same recipe have differing model color descriptions. In particular, review vials 4–6 (dark green versus orange) and vials 7–9 (orange-to-green versus blue). These are review candidates, not confirmed recipe failures. Check target-vial identity and transitions at the clip boundaries.

The model sometimes wraps JSON in Markdown. The parsed files remove that wrapper; raw responses are retained.

Results are stored under each clip: output/20261025-batch01/observation-parsed.json.
