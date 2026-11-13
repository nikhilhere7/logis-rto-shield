# logis frontend

logis — Logistics, worry-free.

React 19, Vite, Tailwind 4, Motion and Anime.js.

    npm install
    cp .env.example .env
    npm run dev          # http://127.0.0.1:5174, expects the Django API on http://127.0.0.1:8000

The dev server always uses port 5174 (`strictPort`): if 5174 is already taken it stops with an error
instead of moving to another port, because the backend only allows requests from 5174 (CORS).

Where things live:

- `src/index.css`            the palette and shared classes. Change a colour here and it changes everywhere.
- `src/components/PixelField.jsx`  the animated pixel background (Anime.js)
- `src/components/charts.jsx`      line, bar, ring, heatmap and factor charts (Motion)
- `src/components/motion.jsx`      Reveal and CountUp helpers
- `src/components/AuthModal.jsx`   the log in / sign up pop-up
- `src/pages/Landing.jsx`          the landing page
- `src/pages/Dashboard.jsx`        the merchant dashboard
- `src/pages/Uploads.jsx`          the three-step upload flow
- `src/data/sample.js`             sample figures shown on the landing page only

If nothing animates: check that your operating system is not set to reduce motion
(Windows: Settings, Accessibility, Visual effects, Animation effects). The site respects that setting.
