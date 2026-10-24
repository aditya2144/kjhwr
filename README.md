# Day-ahead wind outlook

A small web app for a GB electricity buying team. It answers two questions about **national wind generation**:

1. What is the latest wind forecast available at the moment the day-ahead purchase has to be decided?
2. How accurate have those forecasts been, in numbers, so the error can be priced into the decision?

Data comes only from Elexon BMRS: `FUELHH` (actual generation, fuel type `WIND`) and `WINDFOR` (wind forecasts with a `publishTime`). Scope: purchase decisions made in **January 2026**, i.e. delivery days 2 Jan to 1 Feb 2026.

**Live app:** `https://kjhwr-gules.vercel.app`

> **AI disclosure:** this project was built with the help of an AI assistant (Claude, by Anthropic), which wrote most of the first draft of the code and documentation. I reviewed, ran and understand the code.

## How to start the application

### Option 1: Docker (recommended)

```bash
docker compose up --build
```

* App: http://localhost:8080
* API docs (Swagger): http://localhost:8000/docs

### Option 2: without Docker

```bash
# backend (Python 3.11+)
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload --port 8000

# frontend (Node 18+), in a second terminal
cd frontend && npm install && npm run dev      # http://localhost:5173 (proxies /api to :8000)
```

### Tests

```bash
python -m unittest discover -s backend/tests -t . -v
```

### Refreshing the data

The two small data files in `backend/data/` are committed, so the app needs no live API calls. To re-download them from Elexon (no API key needed):

```bash
python backend/scripts/fetch_data.py
```

## Files and directories

```
backend/
  app/
    config.py        every assumption in one place (window, decision cut-off, band percentiles)
    elexon.py        small client for the Elexon API (chunked requests, retry/back-off)
    analysis.py      all the logic, pure pandas, no web code (this is the part to review first)
    store.py         loads the data snapshot and builds the analysis object
    main.py          FastAPI app: thin JSON endpoints over analysis.py
  scripts/fetch_data.py   one-off download of January 2026 data, prints a sanity report
  data/              wind_actuals.csv.gz, wind_forecasts.csv.gz (snapshot from Elexon)
  tests/             unit tests for the decision logic and metrics
  Dockerfile
frontend/            React (Vite) single page app, charts with Recharts
  src/App.jsx              page shell and controls
  src/DecisionSection.jsx  tomorrow's forecast at the decision time
  src/AccuracySection.jsx  accuracy metrics and charts
  src/HorizonSection.jsx   accuracy against forecast lead time
  Dockerfile, nginx.conf   static build served by nginx, /api proxied to the backend
api/index.py         Vercel serverless entry point (exposes the FastAPI app)
vercel.json          Vercel build and routing config
docker-compose.yml   runs backend + frontend together
```

## What the app shows

* **Decision view.** Pick a delivery day and a decision time. The app shows the wind forecast that was the newest one published before that time, a likely range, the weakest three hours, total energy, how fresh the forecast is, how much it changed in the last 6 hours, and (for hindsight) what actually happened.
* **Accuracy.** MAE, RMSE, bias, error as a share of output, a "1 in 20 bad half-hour" figure, plus charts by day, by hour of day and the spread of errors. A naive baseline puts the numbers in context.
* **Lead time.** Error against hours between forecast publication and the half-hour it covers, with the day-ahead decision window highlighted.

## Key design decisions and assumptions

1. **"Latest forecast available" is the core idea.** `WINDFOR` holds many forecasts for the same half-hour, published at different times. For each half-hour of the delivery day I pick the one with the greatest `publishTime` that is **at or before the decision cut-off** (`pandas.merge_asof`, matched per `startTime`). Using a forecast published after the cut-off would be look-ahead and flatter the results; there is a unit test for this.
2. **Decision cut-off (assumption).** Default is **09:00 UK time on the day before delivery**, selectable in the UI (06:00, 09:00, 12:00). I chose it to sit ahead of the morning day-ahead auction gate closures; it is a configurable assumption (`backend/app/config.py`), not a fact from the brief.
3. **Scope.** A decision made on day D is for delivery day D+1, so decisions in January 2026 cover delivery days 2 Jan to 1 Feb. All times are handled as UTC internally and shown in UK time.
4. **Error sign.** `error = forecast − actual`. Positive means the forecast was too high, i.e. less wind arrived than expected, which is the costly direction for a buyer.
5. **Metrics.** MAE, RMSE, bias (mean error), WAPE (total absolute error ÷ total actual), error percentiles. I avoid MAPE because wind output can be close to zero.
6. **Likely range.** The 5th and 95th percentiles of past errors are applied to the forecast. For a given delivery day only **earlier** delivery days are used, so no future information leaks in. The first days of the window have no history; they fall back to the whole month and the UI says so.
7. **Baseline.** Naive guess = actual wind from the same half-hour two days earlier (always known by the cut-off). It shows whether the forecast adds value.
8. **Hourly forecasts vs half-hourly actuals.** `WINDFOR` turned out to be hourly (targets on the hour), while `FUELHH` is half-hourly. I never invent forecast values for accuracy: every metric uses only the real forecast hours (31 days x 24 = 744 points). For the chart and day totals, the missing half-hours are filled by linear interpolation and flagged `native=false` in the code.
9. **Pre-fetched snapshot.** January 2026 is historical and fixed, so the data is downloaded once and committed. That makes the deployment fast, free of rate limits, and reproducible for reviewers. The fetch script is included.

## Limitations

* National level wind only, as specified. No demand, prices or other fuels, so the app does not compute a purchase volume; it quantifies the wind forecast and its error.
* One month of history. Percentile ranges and bias are estimated from roughly 30 days and will move with more data.
* The cut-off time is an assumption (see above).

Contains BMRS data © Elexon Limited copyright and database right 2026.
