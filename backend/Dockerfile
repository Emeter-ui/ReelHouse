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

RUN uv sync --frozen --no-dev

EXPOSE 8080

# Bind to 0.0.0.0:8080 to match fly.toml's internal_port.
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
