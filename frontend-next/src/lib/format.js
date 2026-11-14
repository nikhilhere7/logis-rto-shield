// Indian number formatting: 229005 -> "2,29,005".
// Every helper returns "—" for null, undefined, NaN and Infinity, so those never reach the screen.
const whole = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
export const DASH = "—";
const bad = (n) => n == null || !Number.isFinite(Number(n));

export const count = (n) => (bad(n) ? DASH : whole.format(Math.round(Number(n))));
export const inr = (n) => (bad(n) ? DASH : "₹" + whole.format(Math.round(Number(n))));
export const pct = (n, digits = 1) => (bad(n) ? DASH : `${Number(n).toFixed(digits)}%`);

// 20885824 -> "₹2.09 Cr", 4847083 -> "₹48.5 L"
export function inrShort(n) {
  if (bad(n)) return DASH;
  const v = Number(n);
  if (Math.abs(v) >= 1e7) return `₹${(v / 1e7).toFixed(2)} Cr`;
  if (Math.abs(v) >= 1e5) return `₹${(v / 1e5).toFixed(1)} L`;
  return inr(v);
}

// Money with its sign in front: 25522 -> "+₹25,522", -12481 -> "−₹12,481". Zero has no sign.
export function signedInr(n) {
  if (bad(n)) return DASH;
  const v = Math.round(Number(n));
  return `${v > 0 ? "+" : v < 0 ? "−" : ""}${inr(Math.abs(v))}`;
}

// "2025-12-29" or an ISO timestamp -> "29 Dec 2025"
export function day(value) {
  const d = new Date(value);
  return value && !Number.isNaN(d.getTime()) ? d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : DASH;
}
