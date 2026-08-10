# Deployment Guide

## Architecture

- **Backend:** Cloud Run (single container running FastAPI + pipeline)
- **Frontend:** Vercel (static Vite/React build)

## Critical: Single-Instance Requirement

The backend **must** be deployed with `--min-instances=1 --max-instances=1`.
This is a **correctness requirement**, not a performance tuning suggestion:

- The in-memory `JOBS` store holds active job state — a status poll on a
  different instance than the one running the job would return "not found."
- The file-based response cache is local to a single filesystem — a second
  instance would never see another instance's cache entries.

Autoscaling beyond one instance **silently breaks** both features.
`--min-instances=1` also avoids cold-start delay during judging.

---

## Environment Variables & Secrets

### Backend (Cloud Run)

| Variable | Required | Description |
|----------|----------|-------------|
| `GCP_PROJECT` | Yes | Google Cloud project ID (e.g. `trialgent`) |
| `GCP_LOCATION` | No | Vertex AI region (default: `us-central1`) |
| `PARALLEL_WEB_API_KEY` | Yes | Parallel Search API key (use Secret Manager) |
| `CORS_ALLOWED_ORIGINS` | No | Comma-separated allowed origins. Default `*` (permissive). Set to frontend URL in production (e.g. `https://artgents.vercel.app`) |

### Frontend (Vercel)

| Variable | Required | Description |
|----------|----------|-------------|
| `VITE_API_URL` | Yes | Full Cloud Run backend URL (e.g. `https://artgents-backend-xxxxx-uc.a.run.app`) |

---

## Deployment Steps (Ordered)

### Step 1: One-time IAM setup

Grant the Cloud Run service account permission to call Vertex AI:

```bash
# Find your Cloud Run service account (usually the Compute Engine default)
SA="<PROJECT_NUMBER>-compute@developer.gserviceaccount.com"

gcloud projects add-iam-policy-binding <PROJECT_ID> \
  --member="serviceAccount:${SA}" \
  --role="roles/aiplatform.user"
```

### Step 2: Deploy backend (permissive CORS initially)

```bash
gcloud run deploy artgents-backend \
  --source . \
  --region us-central1 \
  --min-instances=1 \
  --max-instances=1 \
  --allow-unauthenticated \
  --set-env-vars="GCP_PROJECT=trialgent,GCP_LOCATION=us-central1" \
  --set-secrets="PARALLEL_WEB_API_KEY=parallel-web-api-key:latest"
```

Note the deployed backend URL from the output (e.g.
`https://artgents-backend-xxxxx-uc.a.run.app`).

### Step 3: Deploy frontend to Vercel

```bash
cd frontend

# Set the environment variable in Vercel project settings or via CLI:
vercel env add VITE_API_URL production
# Enter the backend URL from Step 2

vercel --prod
```

Note the deployed frontend URL (e.g. `https://artgents.vercel.app`).

### Step 4: Lock down CORS

Redeploy backend with CORS restricted to the actual frontend origin:

```bash
gcloud run services update artgents-backend \
  --region us-central1 \
  --update-env-vars="CORS_ALLOWED_ORIGINS=https://artgents.vercel.app"
```

### Step 5: Verify deployment

```bash
# Health check
curl https://artgents-backend-xxxxx-uc.a.run.app/api/health
# Expected: {"status":"ok"}

# Confirm single-instance config
gcloud run services describe artgents-backend \
  --region us-central1 \
  --format="value(spec.template.spec.containerConcurrency,spec.template.metadata.annotations['autoscaling.knative.dev/minScale'],spec.template.metadata.annotations['autoscaling.knative.dev/maxScale'])"

# Full end-to-end test: open the frontend URL in a browser, upload an
# artwork image, and confirm a complete analysis result is returned.
```

---

## Secret Management

**Never commit secrets to the repo.** Use one of:

1. **Cloud Run Secret Manager integration** (recommended):
   ```bash
   # Create the secret
   echo -n "your-api-key" | gcloud secrets create parallel-web-api-key --data-file=-
   
   # Grant Cloud Run service account access
   gcloud secrets add-iam-policy-binding parallel-web-api-key \
     --member="serviceAccount:${SA}" \
     --role="roles/secretmanager.secretAccessor"
   ```

2. **Direct env var** (simpler but less secure):
   ```bash
   gcloud run services update artgents-backend \
     --region us-central1 \
     --update-env-vars="PARALLEL_WEB_API_KEY=your-key-here"
   ```

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| Job status returns 404 | Request hit a different instance | Confirm `--max-instances=1` is set |
| CORS errors in browser | `CORS_ALLOWED_ORIGINS` doesn't match frontend URL | Update env var (include protocol, no trailing slash) |
| Vertex AI 403 | Service account lacks IAM role | Run the IAM grant from Step 1 |
| WriteTimeout on image upload | Timeout too low | Already fixed: 120s timeout configured |
| Cache misses on repeat requests | Instance restarted | Expected — cache is ephemeral on restarts |
