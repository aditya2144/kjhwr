import { useEffect, useMemo, useState } from "react";
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { getDecision } from "./api.js";
import { C, axisTick } from "./theme.js";
import { fmtDateTime, fmtDayLong, fmtTime, gw, gwSigned } from "./format.js";

function ChartTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null;
  const p = payload[0].payload;
  return (
    <div className="tip">
      <strong>{p.time}</strong>
      <div>Forecast {gw(p.forecast_mw, 2)}</div>
      {p.lower_mw != null && p.upper_mw != null && (
        <div>
          Likely range {gw(p.lower_mw)} to {gw(p.upper_mw)}
        </div>
      )}
      {p.actual_mw != null && <div>Actual {gw(p.actual_mw, 2)}</div>}
      <div className="tip-muted">Forecast made {fmtDateTime(p.published)}</div>
    </div>
  );
}

export default function DecisionSection({ date, cutoff }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setError(null);
    getDecision(date, cutoff)
      .then((d) => live && setData(d))
      .catch((e) => live && setError(e.message))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [date, cutoff]);

  const rows = useMemo(
    () =>
      data
        ? data.series.map((r) => ({
            ...r,
            time: fmtTime(r.t),
            band: r.lower_mw != null && r.upper_mw != null ? [r.lower_mw, r.upper_mw] : null,
          }))
        : [],
    [data]
  );

  if (error) {
    return (
      <section id="decision" className="section">
        <div className="error" role="alert">
          <strong>Could not load the forecast.</strong> {error}
        </div>
      </section>
    );
  }
  if (!data) {
    return (
      <section id="decision" className="section">
        <p className="lede">Loading the forecast…</p>
      </section>
    );
  }

  const s = data.summary;
  const b = data.band;
  const r = data.realised;
  const hasForecast = s.mean_mw != null;
  const lessWind = b.q_high_mw != null ? Math.max(0, b.q_high_mw) : null;
  const moreWind = b.q_low_mw != null ? Math.max(0, -b.q_low_mw) : null;
  const coverage = b.high_pct - b.low_pct;

  const facts = [];
  if (hasForecast) {
    facts.push({
      label: "Total wind energy",
      value: `${s.energy_gwh} GWh`,
      note: "Estimated from the hourly forecast, filled in to half-hours.",
    });
    facts.push({
      label: "Weakest three hours",
      value: gw(s.weakest_3h_mean_mw),
      note: `Starting ${fmtTime(s.weakest_3h_start)}. Lowest single half-hour: ${gw(s.min_mw)} at ${fmtTime(s.min_at)}.`,
    });
    if (lessWind != null) {
      facts.push({
        label: "How far off it can be",
        value: `${gw(lessWind)} less or ${gw(moreWind)} more`,
        note:
          `Wind actually arrived within this range of the forecast in ${coverage}% of forecast hours across the ${b.history_days} earlier delivery days.` +
          (b.in_sample
            ? " This is one of the first days in the window, so the range uses the whole month and is slightly optimistic."
            : ""),
      });
    }
    facts.push({
      label: "How fresh the forecast is",
      value: `${s.horizon_min_h} to ${s.horizon_max_h} hours ahead`,
      note:
        s.first_publish === s.last_publish
          ? `Every hour of the day comes from the run published ${fmtDateTime(s.last_publish)}.`
          : `Runs published ${fmtDateTime(s.first_publish)} to ${fmtDateTime(s.last_publish)}.`,
    });
    if (s.revision_mean_mw != null) {
      facts.push({
        label: `Change in the last ${s.revision_hours} hours`,
        value: gwSigned(s.revision_mean_mw, 2),
        note: `Average shift in the forecast compared with the one available ${s.revision_hours} hours before the decision time (${s.revision_energy_gwh > 0 ? "+" : ""}${s.revision_energy_gwh} GWh over the day).`,
      });
    }
  }
  if (r && r.n > 0) {
    facts.push({
      label: "What actually happened",
      value: `${gw(r.mae_mw, 2)} average miss`,
      note: `The forecast ran ${r.bias_mw > 0 ? "high" : "low"} by ${gw(Math.abs(r.bias_mw), 2)} on average, so ${
        r.bias_mw > 0 ? "less" : "more"
      } wind arrived than expected.`,
    });
  }

  return (
    <section id="decision" className={`section${loading ? " dim" : ""}`} aria-busy={loading}>
      <h1 className="headline">
        {hasForecast
          ? `Wind should supply about ${gw(s.mean_mw)} on average on ${fmtDayLong(data.delivery_date)}.`
          : `No forecast was available at ${data.cutoff_local} for ${fmtDayLong(data.delivery_date)}.`}
      </h1>
      {hasForecast && (
        <p className="lede">
          The peak is {gw(s.max_mw)} at {fmtTime(s.max_at)}; the weakest three hours start at {fmtTime(s.weakest_3h_start)}{" "}
          and average {gw(s.weakest_3h_mean_mw)}. This is the latest forecast published before the decision time,{" "}
          {fmtDateTime(data.cutoff_utc)}.
        </p>
      )}

      <figure className="chart">
        <ResponsiveContainer width="100%" height={360}>
          <ComposedChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={C.rule} strokeDasharray="2 4" vertical={false} />
            <XAxis dataKey="time" interval={5} tick={axisTick} tickLine={false} axisLine={{ stroke: C.rule }} />
            <YAxis
              tickFormatter={(v) => (v / 1000).toFixed(0)}
              tick={axisTick}
              tickLine={false}
              axisLine={false}
              width={36}
              domain={[0, "auto"]}
            />
            <Tooltip content={<ChartTooltip />} />
            <Area dataKey="band" stroke="none" fill={C.forecast} fillOpacity={0.14} isAnimationActive={false} />
            <Line dataKey="earlier_forecast_mw" stroke={C.earlier} strokeWidth={1.5} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
            <Line dataKey="forecast_mw" stroke={C.forecast} strokeWidth={2.5} dot={false} isAnimationActive={false} />
            <Line dataKey="actual_mw" stroke={C.ink} strokeWidth={1.5} dot={false} connectNulls isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
        <figcaption>
          <ul className="legend">
            <li><i className="sw" style={{ background: C.forecast }} /> Forecast at the decision time</li>
            <li><i className="sw band" /> Likely range ({b.low_pct}th to {b.high_pct}th percentile of past misses)</li>
            <li><i className="sw dashed" /> Forecast {s.revision_hours ?? 6} hours earlier</li>
            <li><i className="sw" style={{ background: C.ink }} /> Actual wind, shown for hindsight</li>
          </ul>
          <span className="muted">Gigawatts (GW), UK time. The forecast is published hourly; points between the hours are interpolated for display.</span>
        </figcaption>
      </figure>

      <table className="facts">
        <tbody>
          {facts.map((f) => (
            <tr key={f.label}>
              <th scope="row">{f.label}</th>
              <td className="fact-value">{f.value}</td>
              <td className="fact-note">{f.note}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
