import { motion, useReducedMotion } from "motion/react";
import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { Mark } from "./Logo";
import { EASE } from "./motion";

function Field({ label, error, hint, ...input }) {
  return (
    <div>
      <label htmlFor={input.id} className="sr-only">{label}</label>
      <input {...input} placeholder={label} aria-invalid={error ? "true" : undefined} aria-describedby={error || hint ? `${input.id}-note` : undefined}
        className={`h-14 w-full rounded-2xl border bg-sheet px-4 text-[15px] outline-none transition placeholder:text-graphite focus:border-brand focus:ring-4 focus:ring-brand/15 ${error ? "border-loss" : "border-[#b6c2d3]"}`} />
      {(error || hint) && <p id={`${input.id}-note`} className={`mt-1.5 px-1 text-[13px] ${error ? "text-loss" : "text-graphite"}`}>{error || hint}</p>}
    </div>
  );
}

const POINTS = [
  ["Audit every courier bill", "Each invoice line is priced again from your rate card and the real parcel."],
  ["Trace your COD cash", "Every delivered COD parcel is matched to a remittance, one by one."],
  ["Score orders before they ship", "A model trained on your own history, with reasons you can read."],
];

// Log in and sign up share one pop-up that opens over the landing page.
export default function AuthModal({ mode }) {
  const signup = mode === "signup";
  const auth = useAuth();
  const navigate = useNavigate();
  const from = useLocation().state?.from || "/app";
  const still = useReducedMotion();
  const [form, setForm] = useState({ business_name: "", name: "", email: "", password: "" });
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);
  const close = () => navigate("/");

  useEffect(() => {
    if (auth.user) navigate("/app", { replace: true });
  }, [auth.user, navigate]);
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && navigate("/");
    document.body.style.overflow = "hidden";             // the page behind stays put while the pop-up is open
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", onKey);
    };
  }, [navigate]);
  useEffect(() => setErrors({}), [mode]);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setErrors({});
    try {
      if (signup) await auth.signup(form);
      else await auth.login(form.email, form.password);
      navigate(signup ? "/app" : from, { replace: true });
    } catch (err) {
      const d = err.data && typeof err.data === "object" ? err.data : {};
      const flat = Object.fromEntries(Object.entries(d).map(([k, v]) => [k, Array.isArray(v) ? v[0] : String(v)]));
      const known = Object.keys(flat).some((k) => k in form);
      setErrors(known ? flat : { form: err.status === 401 ? "That email and password don't match. Try again." : err.message });
      setBusy(false);
    }
  };
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  return (
    <motion.div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-ink/55 p-4 backdrop-blur-[2px]"
      initial={still ? false : { opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.2 }} onMouseDown={(e) => e.target === e.currentTarget && close()}>
      <motion.div role="dialog" aria-modal="true" aria-labelledby="auth-title" className="relative my-auto grid w-full max-w-[920px] overflow-hidden rounded-[28px] bg-sheet shadow-2xl md:grid-cols-[1fr_0.9fr]"
        initial={still ? false : { opacity: 0, y: 24, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.35, ease: EASE }}>
        <button type="button" onClick={close} aria-label="Close" className="absolute right-4 top-4 z-10 flex h-11 w-11 items-center justify-center rounded-full text-2xl leading-none transition hover:bg-wash md:text-white md:hover:bg-white/10">×</button>

        <div className="p-7 sm:p-9">
          <Mark size={52} />
          <h2 id="auth-title" className="display mt-5 text-3xl">{signup ? "Create your workspace" : "Welcome back"}</h2>
          <p className="mt-1 text-graphite">{signup ? "Free to start. Your first audit is one upload away." : "Log in to see your numbers."}</p>
          <form onSubmit={submit} className="mt-6 flex flex-col gap-3" noValidate>
            {signup && <Field id="business_name" label="Business name" autoComplete="organization" required autoFocus value={form.business_name} onChange={set("business_name")} error={errors.business_name} />}
            {signup && <Field id="name" label="Your name" autoComplete="name" required value={form.name} onChange={set("name")} error={errors.name} />}
            <Field id="email" label={signup ? "Work email" : "Email"} type={signup ? "email" : "text"} autoComplete="email" required autoFocus={!signup} value={form.email} onChange={set("email")} error={errors.email} />
            <Field id="password" label={signup ? "Create a password" : "Password"} type="password" autoComplete={signup ? "new-password" : "current-password"} required value={form.password} onChange={set("password")}
              error={errors.password} hint={signup ? "Use 8 or more characters, and not only numbers." : undefined} />
            {(errors.form || errors.detail) && <p role="alert" className="rounded-xl border border-loss px-4 py-2.5 text-sm text-loss">{errors.form || errors.detail}</p>}
            <button type="submit" disabled={busy} className="btn mt-1 h-14 rounded-2xl text-base disabled:opacity-60">{busy ? (signup ? "Creating your workspace…" : "Logging in…") : signup ? "Continue" : "Log in"}</button>
          </form>
          <p className="mt-6 text-[15px]">
            {signup ? "Already have an account? " : "New to logis? "}
            <Link to={signup ? "/login" : "/signup"} replace className="font-semibold text-brand-deep underline underline-offset-4">{signup ? "Log in" : "Create an account"}</Link>
          </p>
          <p className="mt-4 text-xs text-graphite">Your files stay in your own workspace. No other seller can see them.</p>
        </div>

        <aside className="hidden flex-col justify-center gap-6 bg-ink p-9 text-white md:flex">
          <p className="font-mono text-xs uppercase tracking-[0.14em] text-gold">What you get</p>
          <ul className="flex flex-col gap-5">
            {POINTS.map(([head, text], i) => (
              <motion.li key={head} className="flex gap-3.5" initial={still ? false : { opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.4, delay: 0.2 + i * 0.1, ease: EASE }}>
                <span aria-hidden="true" className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-[3px] bg-brand" />
                <div><p className="font-semibold">{head}</p><p className="text-sm text-white/70">{text}</p></div>
              </motion.li>
            ))}
          </ul>
          <div className="rounded-2xl border border-white/15 p-5">
            <p className="figure text-4xl">₹2,29,005</p>
            <p className="mt-1 text-sm text-white/70">found for a sample seller across 15,370 shipments</p>
          </div>
        </aside>
      </motion.div>
    </motion.div>
  );
}
