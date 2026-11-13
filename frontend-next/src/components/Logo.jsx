import { Link } from "react-router-dom";

// Placeholder mark: four pixels. Swap this file when the real logo exists.
export function Mark({ size = 30 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" role="img" aria-label="logis logo">
      <rect width="32" height="32" rx="8" fill="#0A2540" />
      <rect x="8" y="8" width="7" height="7" rx="1.5" fill="#635BFF" />
      <rect x="17" y="8" width="7" height="7" rx="1.5" fill="#F8FAFC" />
      <rect x="8" y="17" width="7" height="7" rx="1.5" fill="#F8FAFC" />
      <rect x="17" y="17" width="7" height="7" rx="1.5" fill="#C7A84B" />
    </svg>
  );
}

// tagline: show "Logistics, worry-free." under the name (used on the landing page).
export default function Logo({ to = "/", light = false, tagline = false }) {
  return (
    <Link to={to} aria-label="logis home" className="flex min-h-11 items-center gap-2.5">
      <Mark />
      <span className="flex flex-col leading-none">
        <span className={`display text-xl ${light ? "text-white" : ""}`}>logis</span>
        {tagline && <span className={`mt-1 text-xs ${light ? "text-white/70" : "text-graphite"}`}>Logistics, worry-free.</span>}
      </span>
    </Link>
  );
}
