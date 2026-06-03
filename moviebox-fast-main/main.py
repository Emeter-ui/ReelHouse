"""
FastAPI Microservice for moviebox-api integration
Run with: uvicorn main:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from moviebox_api import Search, Session, MovieDetails, TVSeriesDetails
from moviebox_api.download import (
    DownloadableMovieFilesDetail,
    DownloadableTVSeriesFilesDetail,
    resolve_media_file_to_be_downloaded
)
from moviebox_api.constants import SubjectType
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging
import httpx

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s",
)
logger = logging.getLogger("moviebox_service")

app = FastAPI(title="Makaveli Moviebox Service", version="1.0.0")

# Allow Nuxt.js server to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "https://www.mymuvies.com", "https://app.mymuvies.com"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize moviebox session once (reusable) with VPN proxy
PROXY_URL = "http://qclasojl:0zybf1lw56tl@64.137.96.74:6641"
session = Session(proxy=PROXY_URL)

# ============= HELPER FUNCTIONS =============

def _extract_qualities(files):
    """Safely extract qualities from downloadable files"""
    try:
        if not files or not hasattr(files, 'downloads'):
            return []
        
        qualities = []
        for file in files.downloads:
            try:
                quality_dict = {
                    "quality": str(file.resolution),
                    "format": "MP4",
                    "sizeMb": round(file.size / 1024 / 1024, 2) if hasattr(file, 'size') else 0
                }
                qualities.append(quality_dict)
            except Exception as e:
                logger.warning(f"Could not extract quality: {e}")
                continue
        
        return qualities
    except Exception as e:
        logger.error(f"Error extracting qualities: {e}")
        return []

def _extract_subtitles(files):
    """Safely extract subtitles from files"""
    try:
        if not files or not hasattr(files, 'captions'):
            return []
        
        subtitles = []
        for sub in files.captions:
            try:
                sub_dict = {
                    "language": getattr(sub, 'lanName', getattr(sub, 'language', 'Unknown')),
                    "code": getattr(sub, 'lan', getattr(sub, 'code', 'en')),
                    "url": str(sub.url) if hasattr(sub, 'url') else None
                }
                if sub_dict["url"]:
                    subtitles.append(sub_dict)
            except Exception as e:
                logger.warning(f"Could not extract subtitle: {e}")
                continue
        
        return subtitles
    except Exception as e:
        logger.error(f"Error extracting subtitles: {e}")
        return []

# ============= REQUEST MODELS =============

class SearchRequest(BaseModel):
    query: str
    type: str = "movie"  # "movie" or "series"
    page: int = 1
    per_page: int = 24

class StreamURLRequest(BaseModel):
    page_url: str
    quality: str = "1080p"
    season: Optional[int] = None
    episode: Optional[int] = None

# ============= HEALTH CHECK =============

@app.get("/")
async def root():
    return {
        "service": "Makaveli Moviebox API",
        "status": "running",
        "version": "1.0.0"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# ============= SEARCH =============

@app.post("/api/moviebox/search")
async def search_content(req: SearchRequest):
    """
    Search for movies or TV series
    
    Returns:
        - List of movies/series with metadata
        - Each item includes: id, title, year, poster, rating, description, page_url
    """
    try:
        logger.info(f"Searching for: {req.query} (type: {req.type})")
        
        subject_type = SubjectType.MOVIES if req.type == "movie" else SubjectType.TV_SERIES
        search = Search(
            session, 
            query=req.query, 
            subject_type=subject_type,
            page=req.page,
            per_page=req.per_page
        )
        
        results = await search.get_content_model()
        
        formatted_results = []
        for item in results.items:
            formatted_results.append({
                "id": item.subjectId,
                "title": item.title,
                "year": item.releaseDate.year,
                "release_date": str(item.releaseDate),
                "poster": str(item.cover.url),
                "thumbnail": str(item.cover.thumbnail),
                "rating": item.imdbRatingValue,
                "description": item.description,
                "genres": item.genre,
                "duration": item.duration if hasattr(item, 'duration') else None,
                "type": "movie" if item.subjectType == SubjectType.MOVIES else "series",
                "page_url": item.page_url,
                "country": item.countryName
            })
        
        return {
            "success": True,
            "results": formatted_results,
            "pagination": {
                "current_page": results.pager.page,
                "has_more": results.pager.hasMore,
                "next_page": results.pager.nextPage,
                "total": results.pager.totalCount,
                "per_page": req.per_page
            }
        }
        
    except httpx.HTTPStatusError as e:
        logger.error(
            "Search HTTP error %s for query=%s type=%s page=%s url=%s response=%s",
            e.response.status_code,
            req.query,
            req.type,
            req.page,
            e.request.url if e.request else "unknown",
            e.response.text[:500] if e.response else "no-body",
        )
        raise HTTPException(
            status_code=e.response.status_code,
            detail={
                "message": "Upstream search request failed",
                "status_code": e.response.status_code,
                "url": str(e.request.url) if e.request else None,
            },
        )
    except Exception:
        logger.exception(
            "Unhandled search error for params=%s",
            req.dict(),
        )
        raise HTTPException(status_code=500, detail="Unexpected search failure")

# ============= MOVIE DETAILS =============

@app.get("/api/moviebox/movie/details")
async def get_movie_details(page_url: str = Query(..., description="Movie page URL from search results")):
    """
    Get detailed information about a movie including:
    - Full metadata
    - Cast information
    - Available quality options
    - Available subtitles
    """
    try:
        logger.info(f"Fetching movie details for: {page_url}")
        
        movie_details = MovieDetails(page_url, session)
        content = await movie_details.get_content_model()
        
        # Get downloadable files metadata
        downloadable = DownloadableMovieFilesDetail(session, content)
        files = await downloadable.get_content_model()
        
        return {
            "success": True,
            "movie": {
                "title": content.resData.subject.title,
                "description": content.resData.subject.description,
                "duration": content.resData.subject.duration,
                "release_date": str(content.resData.subject.releaseDate),
                "genres": content.resData.subject.genre,
                "rating": content.resData.subject.imdbRatingValue,
                "country": content.resData.subject.countryName,
                "poster": str(content.resData.subject.cover.url),
                "trailer": content.resData.subject.trailer
            },
            "cast": [],  # Cast info structure changed in moviebox-api, skip for now
            "qualities": _extract_qualities(files),
            "subtitles": _extract_subtitles(files),
            "page_url": page_url
        }
        
    except httpx.HTTPStatusError as e:
        logger.error(
            "Movie details HTTP error %s for page_url=%s url=%s response=%s",
            e.response.status_code,
            page_url,
            e.request.url if e.request else "unknown",
            e.response.text[:500] if e.response else "no-body",
        )
        raise HTTPException(
            status_code=e.response.status_code,
            detail={
                "message": "Upstream movie details request failed",
                "status_code": e.response.status_code,
                "url": str(e.request.url) if e.request else None,
            },
        )
    except Exception:
        logger.exception("Unhandled movie details error for page_url=%s", page_url)
        raise HTTPException(status_code=500, detail="Unexpected movie details failure")

# ============= TV SERIES DETAILS =============

@app.get("/api/moviebox/series/details")
async def get_series_details(page_url: str = Query(..., description="Series page URL from search results")):
    """
    Get detailed information about a TV series including:
    - Full metadata
    - Cast information
    - All seasons and episodes available
    """
    try:
        logger.info(f"Fetching series details for: {page_url}")
        
        series_details = TVSeriesDetails(page_url, session)
        content = await series_details.get_content_model()
        
        return {
            "success": True,
            "series": {
                "title": content.resData.subject.title,
                "description": content.resData.subject.description,
                "release_date": str(content.resData.subject.releaseDate),
                "genres": content.resData.subject.genre,
                "rating": content.resData.subject.imdbRatingValue,
                "country": content.resData.subject.countryName,
                "poster": str(content.resData.subject.cover.url),
                "trailer": content.resData.subject.trailer
            },
            "cast": [],  # Cast info structure changed in moviebox-api, skip for now
            "seasons": [
                {
                    "season_number": season.se,
                    "total_episodes": season.maxEp
                }
                for season in content.resData.resource.seasons
            ],
            "total_seasons": content.resData.resource.total_seasons,
            "page_url": page_url
        }
        
    except httpx.HTTPStatusError as e:
        logger.error(
            "Series details HTTP error %s for page_url=%s url=%s response=%s",
            e.response.status_code,
            page_url,
            e.request.url if e.request else "unknown",
            e.response.text[:500] if e.response else "no-body",
        )
        raise HTTPException(
            status_code=e.response.status_code,
            detail={
                "message": "Upstream series details request failed",
                "status_code": e.response.status_code,
                "url": str(e.request.url) if e.request else None,
            },
        )
    except Exception:
        logger.exception("Unhandled series details error for page_url=%s", page_url)
        raise HTTPException(status_code=500, detail="Unexpected series details failure")

# ============= GET STREAM/DOWNLOAD URL FOR MOVIE =============

@app.get("/api/moviebox/movie/stream-url")
async def get_movie_stream_url(
    page_url: str = Query(..., description="Movie page URL"),
    quality: str = Query("1080p", description="Video quality (360p, 480p, 720p, 1080p, best, worst)")
):
    """
    Get direct CDN URL for streaming/downloading a movie
    
    Returns:
        - stream_url: Direct CDN URL (expires after several hours)
        - quality info
        - available subtitles with URLs
    """
    try:
        logger.info(f"Getting stream URL for movie: {page_url} at {quality}")
        
        # Get movie details
        movie_details = MovieDetails(page_url, session)
        content = await movie_details.get_content_model()
        
        # Get downloadable files
        downloadable = DownloadableMovieFilesDetail(session, content)
        files = await downloadable.get_content_model()
        
        # Check if files are available
        if not files.downloads or len(files.downloads) == 0:
            logger.warning(f"No downloadable files found for: {page_url}")
            raise HTTPException(
                status_code=404, 
                detail="No video files available for this movie. It may not be released yet or not available on the platform."
            )
        
        # Resolve media file by quality
        quality_normalized = quality.upper().replace("P", "P")
        if quality_normalized not in ["360P", "480P", "720P", "1080P", "BEST", "WORST"]:
            quality_normalized = "BEST"
            
        media_file = resolve_media_file_to_be_downloaded(quality_normalized, files)
        
        # Get subtitles
        subtitles = [
            {
                "language": sub.lanName,
                "code": sub.lan,
                "url": str(sub.url)
            }
            for sub in files.captions
        ]
        
        return {
            "success": True,
            "stream_url": str(media_file.url),
            "quality": f"{media_file.resolution}p",
            "size_mb": round(media_file.size / 1024 / 1024, 2),
            "file_size": media_file.size,
            "subtitles": subtitles,
            "title": content.resData.subject.title
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Stream URL error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get stream URL: {str(e)}")

# ============= GET STREAM/DOWNLOAD URL FOR TV SERIES EPISODE =============

@app.get("/api/moviebox/series/stream-url")
async def get_series_stream_url(
    page_url: str = Query(..., description="Series page URL"),
    season: int = Query(..., description="Season number"),
    episode: int = Query(..., description="Episode number"),
    quality: str = Query("1080p", description="Video quality")
):
    """
    Get direct CDN URL for streaming/downloading a specific episode
    
    Returns:
        - stream_url: Direct CDN URL
        - Episode info
        - Available subtitles
    """
    try:
        logger.info(f"Getting stream URL for series episode: {page_url} S{season}E{episode} at {quality}")
        
        # Get series details
        series_details = TVSeriesDetails(page_url, session)
        content = await series_details.get_content_model()
        
        # Get episode files
        downloadable = DownloadableTVSeriesFilesDetail(session, content)
        files = await downloadable.get_content_model(season=season, episode=episode)
        
        # Resolve media file by quality
        quality_normalized = quality.upper().replace("P", "P")
        if quality_normalized not in ["360P", "480P", "720P", "1080P", "BEST", "WORST"]:
            quality_normalized = "BEST"
            
        media_file = resolve_media_file_to_be_downloaded(quality_normalized, files)
        
        # Get subtitles
        subtitles = [
            {
                "language": sub.lanName,
                "code": sub.lan,
                "url": str(sub.url)
            }
            for sub in files.captions
        ]
        
        return {
            "success": True,
            "stream_url": str(media_file.url),
            "quality": f"{media_file.resolution}p",
            "size_mb": round(media_file.size / 1024 / 1024, 2),
            "file_size": media_file.size,
            "season": season,
            "episode": episode,
            "subtitles": subtitles,
            "title": content.resData.subject.title
        }
        
    except Exception as e:
        logger.error(f"Series stream URL error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ============= TRENDING =============

@app.get("/api/moviebox/trending")
async def get_trending(
    type: str = Query("movie", description="Content type: movie or series"),
    page: int = Query(0, description="Page number (starts from 0)")
):
    """Get trending movies or series"""
    try:
        from moviebox_api import Trending
        
        trending = Trending(session, page=page, per_page=18)
        results = await trending.get_content_model()
        
        # Filter by type if specified
        filtered_items = []
        for item in results.items:
            if type == "movie" and item.subjectType == SubjectType.MOVIES:
                filtered_items.append(item)
            elif type == "series" and item.subjectType == SubjectType.TV_SERIES:
                filtered_items.append(item)
            elif type == "all":
                filtered_items.append(item)
        
        formatted_results = [
            {
                "id": item.subjectId,
                "title": item.title,
                "year": item.releaseDate.year,
                "poster": str(item.cover.url),
                "thumbnail": str(item.cover.thumbnail),
                "rating": item.imdbRatingValue,
                "description": item.description,
                "type": "movie" if item.subjectType == SubjectType.MOVIES else "series",
                "page_url": item.page_url
            }
            for item in filtered_items
        ]
        
        return {
            "success": True,
            "results": formatted_results,
            "pagination": {
                "current_page": results.pager.page,
                "has_more": results.pager.hasMore,
                "next_page": results.pager.nextPage
            }
        }
        
    except Exception as e:
        logger.error(f"Trending error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
   
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=10000)
    # uvicorn.run("main:app", host="127.0.0.1", port=8080, reload=True)