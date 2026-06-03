from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


class Settings:
    tmdb_api_key: str
    frontend_origin: str
    tmdb_base_url: str = "https://api.themoviedb.org/3"

    def __init__(self) -> None:
        self.tmdb_api_key = os.environ.get("TMDB_API_KEY", "")
        self.frontend_origin = os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000")
        if not self.tmdb_api_key:
            raise RuntimeError(
                "TMDB_API_KEY is not set. Add it to backend/.env (see .env.example)."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
