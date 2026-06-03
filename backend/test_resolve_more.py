import httpx
import asyncio
import json

async def main():
    api_base = "http://localhost:8003/api"
    # Deadpool & Wolverine
    tmdb_id = 533535
    title = "Deadpool & Wolverine"
    
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(
                f"{api_base}/stream/movie",
                params={"tmdb_id": tmdb_id, "title": title},
                timeout=30,
            )
            data = r.json()
            print(f"Title: {title}")
            print(f"Stream URL: {data.get('stream_url')[:50] if data.get('stream_url') else 'None'}")
            print(f"Qualities: {len(data.get('qualities', []))}")
            print(f"Download Qualities: {len(data.get('download_qualities', []))}")
            
            # Try a title that might be harder
            title2 = "Inside Out 2"
            tmdb_id2 = 1022789
            r = await client.get(
                f"{api_base}/stream/movie",
                params={"tmdb_id": tmdb_id2, "title": title2},
                timeout=30,
            )
            data = r.json()
            print(f"\nTitle: {title2}")
            print(f"Stream URL: {data.get('stream_url')[:50] if data.get('stream_url') else 'None'}")
            print(f"Qualities: {len(data.get('qualities', []))}")
            print(f"Download Qualities: {len(data.get('download_qualities', []))}")

        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
