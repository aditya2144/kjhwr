const TZ = "Europe/London";

export const fmtTime = (iso) =>
  iso
    ? new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: TZ }).format(new Date(iso))
    : "–";

export const fmtDayFromIso = (iso) =>
  iso
    ? new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: TZ }).format(new Date(iso))
    : "–";

export const fmtDateTime = (iso) => (iso ? `${fmtDayFromIso(iso)}, ${fmtTime(iso)}` : "–");

// "2026-01-15" -> "Thu 15 Jan"
export const fmtDay = (isoDate) =>
  new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" }).format(
    new Date(`${isoDate}T12:00:00Z`)
  );

export const fmtDayLong = (isoDate) =>
  new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" }).format(
    new Date(`${isoDate}T12:00:00Z`)
  );

export const addDays = (isoDate, n) => {
  const d = new Date(`${isoDate}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};

export const gw = (mw, digits = 1) => (mw == null ? "–" : `${(mw / 1000).toFixed(digits)} GW`);
export const gwSigned = (mw, digits = 1) =>
  mw == null ? "–" : `${mw > 0 ? "+" : mw < 0 ? "−" : ""}${(Math.abs(mw) / 1000).toFixed(digits)} GW`;
export const pct = (v, digits = 1) => (v == null ? "–" : `${v.toFixed(digits)}%`);

export const fmtDayShort = (isoDate) =>
  new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC" }).format(
    new Date(`${isoDate}T12:00:00Z`)
  );
