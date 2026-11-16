# Subly Frontend

React, TypeScript, Tailwind CSS, and Vite frontend for [project_backend](https://github.com/X4v10uR/project_backend).

## Run locally

Use Node.js 20.19+ on the 20.x line, or 22.12+. Start Django on `http://127.0.0.1:8000` and open a terminal in this repository.

```powershell
npm ci
npm run dev
```

Open [Subly](http://127.0.0.1:5173). If Django is listening on a different address, copy `.env.example` to `.env` and set `BACKEND_URL`. Vite proxies the Django routes and WebSocket connection from the frontend origin so sessions and CSRF work in the browser.

## Build

```powershell
npm run build
npm run preview
```

The build runs the TypeScript check and writes the production bundle to `dist/`.

For a production host, serve `dist/` with an `index.html` fallback for React routes. Route `/api/`, `/media/`, `/ws/`, `/admin/`, and `/accounts/password-reset/` to Django on the same public origin. Serve Django’s collected assets under `/static/admin/`, `/static/css/dist/`, `/static/dashboard/`, `/static/female_memoji/`, and `/static/male_memoji/`. Set Django’s `SITE_URL` to the public HTTPS origin. Sessions and CSRF cookies default to Secure when that URL uses HTTPS.
