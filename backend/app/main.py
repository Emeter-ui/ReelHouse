from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routes import captions, debug, healthz, proxy, stream, tmdb

settings = get_settings()

app = FastAPI(title="Reelhouse Backend", version="0.1.0")

origins = [
    "http://localhost:3000",
    "http://localhost:8003",
    "https://reel-house-ym69.vercel.app",
    "https://reel-house-mocha.vercel.app",
    "https://reelmuvies.netlify.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://.*\.vercel\.app|https://.*\.netlify\.app|http://localhost:.*",
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(healthz.router, prefix="/api")
app.include_router(tmdb.router, prefix="/api")
app.include_router(stream.router, prefix="/api")
app.include_router(proxy.router, prefix="/api")
app.include_router(captions.router, prefix="/api")
app.include_router(debug.router, prefix="/api")

@app.get("/")
def root() -> dict[str, str]:
    return {"name": "reelhouse-backend", "docs": "/docs"}