"""FastAPI application for Artgents.

Entry point: uvicorn artgents.api.app:app
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from artgents.config import settings

app = FastAPI(
    title="Artgents",
    description="Multi-Agent Fine Art Provenance & Curation Studio",
    version="0.1.0",
)

# CORS — controlled by CORS_ALLOWED_ORIGINS env var.
# Default "*" is permissive for local dev; in production set to the
# actual frontend origin (e.g. "https://artgents.vercel.app").
# Multiple origins can be comma-separated.
_origins = [o.strip() for o in settings.cors_allowed_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from artgents.api.routes import router  # noqa: E402

app.include_router(router)
