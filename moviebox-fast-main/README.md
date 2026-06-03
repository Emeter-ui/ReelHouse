# Makaveli Moviebox Python Service

FastAPI microservice that wraps moviebox-api to provide streaming URLs for movies and TV series.

## Setup

1. **Install Python 3.10+**
   ```bash
   python --version  # Should be 3.10 or higher
   ```

2. **Install Dependencies**
   ```bash
   cd python-service
   pip install -r requirements.txt
   ```

3. **Run the Service**
   ```bash
   # Development mode with auto-reload
   uvicorn main:app --reload --port 8000
   
   # Or using Python directly
   python main.py
   ```

4. **Test the API**
   - Open browser: https://moviebox-fast-pythonvista7008-6si52h4e.apn.leapcell.dev
   - API docs: https://moviebox-fast-pythonvista7008-6si52h4e.apn.leapcell.dev/docs
   - Health check: https://moviebox-fast-pythonvista7008-6si52h4e.apn.leapcell.dev/health

## API Endpoints

### Search
- `POST /api/moviebox/search` - Search movies/series
  
### Movie
- `GET /api/moviebox/movie/details` - Get movie details
- `GET /api/moviebox/movie/stream-url` - Get stream URL for movie

### TV Series
- `GET /api/moviebox/series/details` - Get series details
- `GET /api/moviebox/series/stream-url` - Get stream URL for episode

### Trending
- `GET /api/moviebox/trending` - Get trending content

## Environment Variables

Optional: Create `.env` file:
```bash
# Mirror host (optional, defaults to h5.aoneroom.com)
MOVIEBOX_API_HOST=moviebox.ph
```

## Architecture

```
Nuxt.js (Port 3000)
    ↓
FastAPI (Port 8000) - This service
    ↓
moviebox-api library
    ↓
moviebox.ph API
    ↓
CDN (direct to user browser)
```

## Deployment

### Production

```bash
# Install production server
pip install gunicorn

# Run with gunicorn
gunicorn main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Docker (Optional)

Create `Dockerfile`:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Run:
```bash
docker build -t makaveli-moviebox .
docker run -p 8000:8000 makaveli-moviebox
```

## Notes

- The service runs on port 8000 by default
- CORS is configured to allow requests from localhost:3000 (Nuxt.js)
- All streaming URLs are temporary and expire after several hours
- No data is stored - this is a stateless service

# moviebox-fast
