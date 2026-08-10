# Design: Deployment

## Division of labor

Kiro prepares the artifacts (Dockerfile, config, code changes for
CORS/env vars, a deployment instructions doc). The actual
gcloud/vercel deploy commands are run by developer personally — deployment
commands touch real cloud accounts, billing, and credentials that
Kiro does not have and should not attempt to use.

## Backend: Dockerfile

```
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev

COPY src/ src/
COPY config/ config/

ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["uv", "run", "uvicorn", "artgents.api.app:app", "--host", "0.0.0.0", "--port", "8080"]
```

Cloud Run expects the container to listen on $PORT (defaults to 8080)
- confirm the actual app entrypoint module path matches
artgents.api.app:app (check the real file, this may differ depending
on how it was actually structured when built).

## Backend: deploy command reference (for developer to run)

```
gcloud run deploy artgents-backend \
  --source . \
  --region us-central1 \
  --min-instances=1 \
  --max-instances=1 \
  --allow-unauthenticated \
  --set-env-vars="GCP_PROJECT=trialgent,GCP_LOCATION=us-central1" \
  --set-secrets="PARALLEL_WEB_API_KEY=parallel-api-key:latest"
```

--min-instances=1 --max-instances=1 is non-negotiable per
requirements.md - this is what makes the single-instance JOBS/cache
design actually hold in production, not just in local testing.

IAM grant needed once, before first deploy:
```
gcloud projects add-iam-policy-binding trialgent \
  --member="serviceAccount:<cloud-run-service-account>" \
  --role="roles/aiplatform.user"
```

## CORS update

Change the permissive dev default (per the API spec) to the actual
Vercel frontend origin once known. This has to be a two-step process in
practice: deploy backend first (get its URL), deploy frontend pointing
at that backend URL (get the frontend's URL), then redeploy the backend
with CORS locked to the real frontend origin. Document this ordering
clearly in the deployment instructions doc.

## Frontend: environment variable wiring

Confirm frontend/src/api/client.ts (or wherever the API base URL is
defined) reads from an environment variable
(import.meta.env.VITE_API_URL for Vite) rather than a hardcoded
localhost value - check the actual current code, since this may
already be correct or may need a small fix depending on how it was
originally built.

## Deployment instructions doc

Create DEPLOYMENT.md at the repo root with the exact ordered steps:
1. Deploy backend (permissive CORS initially)
2. Note backend URL
3. Deploy frontend with VITE_API_URL set to backend URL
4. Note frontend URL
5. Redeploy backend with CORS locked to frontend URL
6. Verify GET /api/health on deployed backend
7. Verify a full real analysis run end-to-end against both deployed
   URLs

## Testing approach

No new automated tests for deployment itself (infrastructure, not
application logic) - verification is the manual end-to-end check in
requirements.md's acceptance criteria, run by developer against the real
deployed URLs.