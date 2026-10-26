# FluidCheck service

A FastAPI service that wraps the team's Python model and returns one JSON
answer per vial: verdict, colours, ranked causes and an explanation. The C#
web app (or any front end) calls it over HTTP.

**It runs today with placeholder model values.** Replace the bundle with the
notebook fit before trusting any verdict.

## Quick start (Windows, python.org Python 3.12)

```
cd fluidcheck-service
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
pytest -q
uvicorn app.main:app --reload
```

Then open:
- http://127.0.0.1:8000/docs  for interactive API docs (try every endpoint in the browser)
- http://127.0.0.1:8000/demo/ for an upload page that shows the verdict card

## How it is put together

```
fluidcheck-service/
├── fluidcheck/            the model as a plain Python package (no web code)
│   ├── schemas.py         request/response shapes = the team contract
│   ├── bundle.py          loads model_bundle/
│   ├── measure.py         empty + full frame -> absorbance, Lab, volume
│   ├── color.py           expected colour, carryover, ΔE2000
│   └── diagnose.py        verdict, cause ranking, explanation, queue risk
├── model_bundle/          what the notebooks produce (manifest/config/params)
├── app/main.py            FastAPI: loads the bundle once, exposes endpoints
├── app/static/index.html  demo page
├── scripts/export_bundle.py   writes a bundle from notebook results
├── tests/                 model tests + API tests
└── Dockerfile
```

The rule: **the notebook and the API import the same `fluidcheck` package.**
Never copy model code into `app/`.

## Plugging in the team's model

| What the team produces | Where it goes |
| --- | --- |
| Fitted dye colours, residue volume, thresholds, vial region | `export_bundle(...)` from the notebook -> `model_bundle/`, restart the API |
| A segmentation model (ONNX) | add `onnxruntime` to requirements, load it in `bundle.py`, use it in `measure.liquid_mask()` |
| A better cause scorer | replace the rules block in `diagnose.diagnose()` |
| Cosmos Reason explanations | replace `_explain()`, keep the template as the fallback, set `explanation_source="cosmos"` |

Field names in `schemas.py` must not change without the whole team: the
front end depends on them.

## Endpoints

| Method | Path | Trigger | Body |
| --- | --- | --- | --- |
| GET | `/health` | app start-up check | – |
| POST | `/analyze` | T2, a fill finished | multipart: `empty`, `full` images; `recipe` JSON; optional `prev_recipe` JSON, `batch_position`, `vial_id`, `tank_flags` JSON list |
| POST | `/queue/risk` | T1, queue changed | JSON: `{"queue": [recipes...], "last_run": recipe}` |
| POST | `/recheck` | T3, cap/seal | returns 501 until cap/seal calibration exists |

A recipe is `{"id": "7", "t100_ml": 20, "t200_ml": 0, "t400_ml": 50}`.

```
curl -X POST http://127.0.0.1:8000/analyze ^
  -F empty=@empty.png -F full=@full.png ^
  -F "recipe={\"id\":\"7\",\"t100_ml\":20,\"t400_ml\":50}" ^
  -F "prev_recipe={\"id\":\"6\",\"t100_ml\":30,\"t200_ml\":10}" ^
  -F batch_position=1
```

## Calling it from the C# app

Mirror `VialResult` as C# records (System.Text.Json maps snake_case with
`JsonNamingPolicy.SnakeCaseLower`), then:

```csharp
var json = new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower };
using var form = new MultipartFormDataContent
{
    { new ByteArrayContent(emptyPng), "empty", "empty.png" },
    { new ByteArrayContent(fullPng),  "full",  "full.png"  },
    { new StringContent(JsonSerializer.Serialize(recipe, json)), "recipe" },
    { new StringContent(JsonSerializer.Serialize(prev, json)),   "prev_recipe" },
    { new StringContent("1"), "batch_position" },
};
var res = await http.PostAsync("http://localhost:8000/analyze", form);
res.EnsureSuccessStatusCode();
var result = await res.Content.ReadFromJsonAsync<VialResult>(json);
```

Server-to-server calls like this need no CORS. If a browser front end on
another port calls the API directly, list its origin in the
`FLUIDCHECK_CORS_ORIGINS` environment variable (comma-separated).

## Docker

```
docker build -t fluidcheck .
docker run -p 8000:8000 fluidcheck
```

To try a new bundle without rebuilding:
`docker run -p 8000:8000 -v %cd%\model_bundle:/srv/model_bundle fluidcheck`
