"""FastAPI application for Artgents.

Entry point: uvicorn artgents.api.app:app
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Artgents",
    description="Multi-Agent Fine Art Provenance & Curation Studio",
    version="0.1.0",
)

# CORS — permissive dev default; tighten before submission
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict to actual frontend origin before production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from artgents.api.routes import router  # noqa: E402

app.include_router(router)
