FROM python:3.12-slim

# uv binary (same tool you use locally) from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies in a cached layer. The project is a package
# (hatch builds ./app and ./fzmovies_api), so the source must be present
# before `uv sync` can build/install it.
COPY pyproject.toml uv.lock ./
COPY app ./app
COPY fzmovies_api ./fzmovies_api
COPY moviebox_api ./moviebox_api

RUN uv sync --frozen --no-dev

EXPOSE 8080

# Bind to 0.0.0.0 on $PORT if the host injects one (Railway does), else 8080
# (Fly). `sh -c` is what lets the CMD substitute the env var.
CMD ["sh", "-c", "uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
