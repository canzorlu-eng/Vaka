# Vaka frontend

React 19 (Create React App + craco), Tailwind CSS and shadcn/ui primitives. In production the build is served by the
FastAPI backend from the same origin (`REACT_APP_BACKEND_URL` is empty), see the root `Dockerfile`.

```bash
npm ci --legacy-peer-deps
npm start                                  # dev server on :3000, expects the API on REACT_APP_BACKEND_URL (frontend/.env)
REACT_APP_BACKEND_URL= npm run build       # same-origin production build
```

Layout: `src/pages` (routes), `src/components` (UI), `src/context` (auth, language), `src/lib/api.js` (API client with
cookie sessions and friendly error toasts), `src/i18n.js` (Turkish and English strings), `src/index.css` (design tokens).

See the root [README](../README.md) for the full picture.
