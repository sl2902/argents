# Tasks: Deployment

- [ ] 1. Create Dockerfile at repo root (backend), matching the
      project's actual uv-based dependency setup and confirming the
      real app entrypoint module path
- [ ] 2. Create .dockerignore (exclude tests, .kiro/, frontend/,
      uploads/outputs directories, etc. - keep the image lean)
- [ ] 3. Confirm/fix frontend API base URL to read from VITE_API_URL
      (or equivalent) rather than a hardcoded localhost value
- [ ] 4. Update CORS config to be trivially switchable between a dev
      default and a production origin (e.g. via an environment
      variable), so the two-step deploy-then-lock-down process
      described in design.md doesn't require a code change each time
- [ ] 5. Create DEPLOYMENT.md at repo root with the exact ordered
      deployment steps from design.md
- [ ] 6. Document required environment variables/secrets (GCP project,
      GCP region, Parallel API key) clearly in DEPLOYMENT.md
- [ ] 7. Document the one-time IAM grant needed for Cloud Run's service
      account to call Vertex AI

Steps 8+ are run by developer personally, not Kiro, per design.md's division
of labor - listed here for tracking, not as Kiro tasks:

- [ ] 8. (Developer) Deploy backend to Cloud Run with --min-instances=1
      --max-instances=1
- [ ] 9. (Developer) Grant Vertex AI IAM role to the Cloud Run service
      account
- [ ] 10. (Developer) Deploy frontend to Vercel with VITE_API_URL set
- [ ] 11. (Developer) Redeploy backend with CORS locked to the real frontend
       origin
- [ ] 12. (Developer) Verify GET /api/health against the deployed backend
- [ ] 13. (Developer) Verify a full real analysis run end-to-end against both
       deployed URLs
- [ ] 14. (Developer) Confirm via gcloud run services describe that exactly
       one instance is configured, not just assumed from deploy flags