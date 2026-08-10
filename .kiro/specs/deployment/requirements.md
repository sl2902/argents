# Requirements: Deployment

## Purpose

Deploy the backend (FastAPI + four-agent pipeline) and frontend
(React/Vite) to real, publicly accessible URLs a judge can use during
the judging window, without payment or credentials of their own.

## Backend — Cloud Run

- Deployed as a container (Dockerfile, `uv`-based build matching the
  existing dependency setup).
- **Single instance, enforced at deploy time** — `--min-instances=1
  --max-instances=1`. This is not a preference, it's a correctness
  requirement: the in-memory `JOBS` store and the file-based response
  cache are both explicitly scoped as single-instance only (see
  `.kiro/specs/response-cache/requirements.md` and the API spec's
  "Job store" section) — autoscaling beyond one instance would silently
  break both (a status poll or cache check could land on a different
  instance than the one holding the data). `--min-instances=1` also
  avoids cold-start delay during judging, at the cost of continuous
  billing — acceptable given the fixed judging window.
- Service account has the IAM role needed to call Vertex AI
  (`roles/aiplatform.user` at minimum) — Cloud Run's default compute
  service account may not have this by default; must be explicitly
  granted.
- Environment variables/secrets needed: GCP project ID, GCP region,
  Parallel Search API key. Secrets go through Cloud Run's secret
  manager integration or environment variables set at deploy time —
  never committed to the repo.
- CORS updated from the permissive dev default (per the API spec) to
  the actual deployed frontend origin, once that URL is known —
  tightening this is explicitly called out as a pre-submission task in
  the existing API spec.

## Frontend — Vercel

Vercel is used for the React frontend, a standard fit for a Vite-built
static React app.

- Deployed from the `frontend/` directory.
- `VITE_API_URL` (or equivalent) environment variable pointing at the
  deployed Cloud Run backend URL — the frontend must not hardcode
  `localhost` anywhere in the built artifact.

## Acceptance criteria

- A judge can open the deployed frontend URL, upload an image, and get
  a complete result — no local setup, no API key of their own, no
  payment.
- Cloud Run backend is confirmed running with exactly one instance
  (verify via `gcloud run services describe`, not just assumed from
  the deploy flags).
- `GET /api/health` responds correctly against the deployed backend
  URL.
- A full real analysis run succeeds end-to-end against the deployed
  backend + frontend, not just against localhost.
- CORS is scoped to the actual frontend origin, not a wildcard, before
  final submission.
- No secrets (API keys, GCP credentials) appear in the repo, the
  frontend's built JS bundle, or any committed config file.

## Out of scope

- No custom domain — default Cloud Run/Vercel URLs are fine for
  judging purposes.
- No CI/CD pipeline — manual deploy is acceptable given the timeline.