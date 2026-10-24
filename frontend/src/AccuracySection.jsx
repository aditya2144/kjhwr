import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { C, axisTick } from "./theme.js";
import { fmtDayShort, gw, gwSigned, pct } from "./format.js";

const axisProps = { tick: axisTick, tickLine: false, axisLine: { stroke: C.rule } };

function Mini({ title, text, children }) {
  return (
    <figure className="mini">
      <h3>{title}</h3>
      <p className="muted">{text}</p>
      <ResponsiveContainer width="100%" height={220}>
        {children}
      </ResponsiveContainer>
    </figure>
  );
}

export default function AccuracySection({ data, cutoff }) {
  if (!data) {
    return (
      <section id="accuracy" className="section">
        <p className="lede">Loading accuracy…</p>
      </section>
    );
  }
  const o = data.overall;
  const days = data.daily.length;
  const b = data.baseline;

  const daily = data.daily.map((d) => ({ ...d, label: fmtDayShort(d.date) }));
  const byHour = data.by_hour.map((h) => ({ ...h, label: String(h.hour).padStart(2, "0") }));
  const hist = data.histogram.map((h) => ({ ...h, label: (h.from_mw / 1000).toFixed(1) }));

  const metrics = [
    ["Mean absolute error", gw(o.mae_mw, 2), "The average size of the miss, in either direction."],
    ["Root mean square error", gw(o.rmse_mw, 2), "Like the mean error, but big misses count for more."],
    ["Error as a share of output", pct(o.wape_pct), "Total miss divided by total wind that actually blew."],
    ["Bias", gwSigned(o.bias_mw, 2), "Positive means forecasts ran too high: less wind arrived than expected."],
    ["Bad hour (1 in 20)", gw(o.p95_error_mw, 2), "In one forecast hour in twenty, wind came in at least this far below forecast."],
    ["Hours forecast too high", pct(o.over_forecast_share_pct, 0), "Share of forecast hours where less wind arrived than forecast."],
    ["Forecast hours checked", String(o.n), `${days} delivery days of hourly forecasts, decided at ${cutoff} the day before.`],
  ];

  return (
    <section id="accuracy" className="section">
      <h2>How accurate has the forecast been?</h2>
      <p className="lede">
        Across {days} delivery days, the forecast available at {cutoff} on the day before missed by {gw(o.mae_mw)} on
        average, which is {pct(o.wape_pct)} of the wind that actually blew. It ran {o.bias_mw > 0 ? "high" : "low"} by{" "}
        {gw(Math.abs(o.bias_mw), 2)} on average.
        {b && b.improvement_pct != null && (
          <>
            {" "}
            A naive guess ({b.description}) misses by {gw(b.mae_mw)}, so the forecast is {b.improvement_pct.toFixed(0)}%{" "}
            {b.improvement_pct >= 0 ? "better" : "worse"}.
          </>
        )}
      </p>

      <table className="facts">
        <tbody>
          {metrics.map(([label, value, note]) => (
            <tr key={label}>
              <th scope="row">{label}</th>
              <td className="fact-value">{value}</td>
              <td className="fact-note">{note}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="grid3">
        <Mini title="Miss by delivery day" text="Average miss for each day, in GW. Taller bars are harder days.">
          <BarChart data={daily} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={C.rule} strokeDasharray="2 4" vertical={false} />
            <XAxis dataKey="label" interval={4} {...axisProps} />
            <YAxis tickFormatter={(v) => (v / 1000).toFixed(1)} tick={axisTick} tickLine={false} axisLine={false} width={36} />
            <Tooltip formatter={(v) => gw(v, 2)} />
            <Bar dataKey="mae_mw" name="Average miss" fill={C.forecast} isAnimationActive={false} />
          </BarChart>
        </Mini>

        <Mini title="Bias by hour of day" text="Red: forecast too high (less wind than expected). Teal: too low.">
          <BarChart data={byHour} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={C.rule} strokeDasharray="2 4" vertical={false} />
            <XAxis dataKey="label" interval={3} {...axisProps} />
            <YAxis tickFormatter={(v) => (v / 1000).toFixed(1)} tick={axisTick} tickLine={false} axisLine={false} width={36} />
            <Tooltip formatter={(v) => gwSigned(v, 2)} />
            <Bar dataKey="bias_mw" name="Average bias" isAnimationActive={false}>
              {byHour.map((h) => (
                <Cell key={h.hour} fill={h.bias_mw > 0 ? C.risk : C.forecast} />
              ))}
            </Bar>
          </BarChart>
        </Mini>

        <Mini title="Spread of misses" text="How many forecast hours missed by each amount, in GW. Right of zero means too high.">
          <BarChart data={hist} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} barCategoryGap={1}>
            <CartesianGrid stroke={C.rule} strokeDasharray="2 4" vertical={false} />
            <XAxis dataKey="label" interval={Math.max(0, Math.floor(hist.length / 6))} {...axisProps} />
            <YAxis tick={axisTick} tickLine={false} axisLine={false} width={36} />
            <Tooltip formatter={(v) => `${v} forecast hours`} labelFormatter={(l) => `Miss starting at ${l} GW`} />
            <Bar dataKey="count" name="Forecast hours" isAnimationActive={false}>
              {hist.map((h) => (
                <Cell key={h.from_mw} fill={h.from_mw >= 0 ? C.risk : C.forecast} />
              ))}
            </Bar>
          </BarChart>
        </Mini>
      </div>
    </section>
  );
}
