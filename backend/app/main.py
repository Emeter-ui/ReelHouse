from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routes import healthz, proxy, stream, tmdb

settings = get_settings()

app = FastAPI(title="Reelhouse Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:3001"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(healthz.router, prefix="/api")
app.include_router(tmdb.router, prefix="/api")
app.include_router(stream.router, prefix="/api")
app.include_router(proxy.router, prefix="/api")


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "reelhouse-backend", "docs": "/docs"}
