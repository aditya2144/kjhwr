const BASE = import.meta.env.VITE_API_BASE || "";

async function get(path, params = {}) {
  const qs = new URLSearchParams(params).toString();
  const res = await fetch(`${BASE}${path}${qs ? `?${qs}` : ""}`);
  if (!res.ok) {
    let message = res.statusText;
    try {
      message = (await res.json()).detail || message;
    } catch {
      /* body was not JSON */
    }
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }
  return res.json();
}

export const getMeta = () => get("/api/meta");
export const getDecision = (deliveryDate, cutoff) =>
  get("/api/decision", { delivery_date: deliveryDate, cutoff });
export const getAccuracy = (cutoff) => get("/api/accuracy", { cutoff });
export const getHorizon = (binHours = 3) => get("/api/horizon", { bin_hours: binHours });
