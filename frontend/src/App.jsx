import { useEffect, useState } from "react";
import { getAccuracy, getHorizon, getMeta } from "./api.js";
import DecisionSection from "./DecisionSection.jsx";
import AccuracySection from "./AccuracySection.jsx";
import HorizonSection from "./HorizonSection.jsx";
import { addDays, fmtDay } from "./format.js";

export default function App() {
  const [meta, setMeta] = useState(null);
  const [date, setDate] = useState(null);
  const [cutoff, setCutoff] = useState(null);
  const [accuracy, setAccuracy] = useState(null);
  const [horizon, setHorizon] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getMeta()
      .then((m) => {
        setMeta(m);
        setDate(m.last_delivery); // the most recent decision in the window
        setCutoff(m.default_cutoff);
      })
      .catch((e) => setError(e.message));
    getHorizon(3).then(setHorizon).catch(() => {});
  }, []);

  useEffect(() => {
    if (!cutoff) return undefined;
    let live = true;
    setAccuracy(null);
    getAccuracy(cutoff)
      .then((a) => live && setAccuracy(a))
      .catch((e) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [cutoff]);

  if (error) {
    return (
      <main className="wrap">
        <div className="error" role="alert">
          <strong>The service is not available.</strong> {error}
        </div>
      </main>
    );
  }
  if (!meta || !date) {
    return (
      <main className="wrap">
        <p className="lede">Loading…</p>
      </main>
    );
  }

  const canPrev = date > meta.first_delivery;
  const canNext = date < meta.last_delivery;

  return (
    <>
      <header className="top">
        <div className="wrap bar">
          <div>
            <div className="brand">Day-ahead wind outlook</div>
            <div className="muted">Great Britain, national wind generation. Pilot built on Elexon data.</div>
          </div>
          <div className="controls">
            <div className="control">
              <label htmlFor="day">Delivery day</label>
              <div className="stepper">
                <button type="button" onClick={() => setDate(addDays(date, -1))} disabled={!canPrev} aria-label="Previous day">
                  ‹
                </button>
                <input
                  id="day"
                  type="date"
                  value={date}
                  min={meta.first_delivery}
                  max={meta.last_delivery}
                  onChange={(e) => e.target.value && setDate(e.target.value)}
                />
                <button type="button" onClick={() => setDate(addDays(date, 1))} disabled={!canNext} aria-label="Next day">
                  ›
                </button>
              </div>
              <span className="muted small">{fmtDay(date)}</span>
            </div>
            <div className="control">
              <label htmlFor="cutoff">Decide by (UK time, day before)</label>
              <select id="cutoff" value={cutoff} onChange={(e) => setCutoff(e.target.value)}>
                {meta.cutoff_options.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
      </header>

      <main className="wrap">
        <DecisionSection date={date} cutoff={cutoff} />
        <AccuracySection data={accuracy} cutoff={cutoff} />
        <HorizonSection horizon={horizon} decisionRange={accuracy ? accuracy.decision_horizon_h : null} />
      </main>

      <footer className="wrap foot">
        <p>
          Forecasts and outturn are the national wind figures from Elexon's FUELHH and WINDFOR datasets. The likely range
          comes from how far earlier forecasts missed, using only days before the one shown. Contains BMRS data © Elexon
          Limited copyright and database right 2026.
        </p>
      </footer>
    </>
  );
}
