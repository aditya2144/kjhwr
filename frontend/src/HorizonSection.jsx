import { CartesianGrid, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { C, axisTick } from "./theme.js";
import { gw } from "./format.js";

export default function HorizonSection({ horizon, decisionRange }) {
  if (!horizon || !horizon.bins.length) return null;
  const bins = horizon.bins.map((b) => ({ ...b, label: `${b.from_h}–${b.to_h}` }));
  const first = bins[0];
  const last = bins[bins.length - 1];

  const labelFor = (h) => {
    const hit = bins.find((b) => h >= b.from_h && h < b.to_h);
    return hit ? hit.label : null;
  };
  const x1 = decisionRange && decisionRange.min != null ? labelFor(decisionRange.min) : null;
  const x2 = decisionRange && decisionRange.max != null ? labelFor(decisionRange.max) : null;

  return (
    <section id="horizon" className="section">
      <h2>Does the forecast improve closer to delivery?</h2>
      <p className="lede">
        Forecasts made {first.to_h} hours or less before delivery missed by {gw(first.mae_mw)} on average; those made{" "}
        {last.from_h} to {last.to_h} hours ahead missed by {gw(last.mae_mw)}.
        {x1 && x2 && (
          <>
            {" "}
            The day-ahead decision has to use forecasts that are {decisionRange.min} to {decisionRange.max} hours ahead,
            the shaded band below.
          </>
        )}
      </p>
      <figure className="chart">
        <ResponsiveContainer width="100%" height={320}>
          <LineChart data={bins} margin={{ top: 8, right: 32, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={C.rule} strokeDasharray="2 4" vertical={false} />
            {x1 && x2 && <ReferenceArea x1={x1} x2={x2} fill={C.forecast} fillOpacity={0.1} stroke="none" />}
            <XAxis dataKey="label" tick={axisTick} tickLine={false} axisLine={{ stroke: C.rule }} interval={1} />
            <YAxis tickFormatter={(v) => (v / 1000).toFixed(1)} tick={axisTick} tickLine={false} axisLine={false} width={36} domain={[0, "auto"]} />
            <Tooltip formatter={(v) => gw(v, 2)} labelFormatter={(l) => `${l} hours before delivery`} />
            <Line dataKey="mae_mw" name="Average miss" stroke={C.forecast} strokeWidth={2.5} dot={{ r: 3 }} isAnimationActive={false} />
            <Line dataKey="rmse_mw" name="Root mean square miss" stroke={C.earlier} strokeWidth={1.5} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
        <figcaption>
          <ul className="legend">
            <li><i className="sw" style={{ background: C.forecast }} /> Average miss</li>
            <li><i className="sw dashed" /> Root mean square miss (big misses count more)</li>
          </ul>
          <span className="muted">Gigawatts (GW). Horizontal axis: hours between publishing the forecast and the hour it covers.</span>
        </figcaption>
      </figure>
    </section>
  );
}
