import httpx
import asyncio
import json

async def test_movie(title, tmdb_id):
    api_base = "http://localhost:8003/api"
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(
                f"{api_base}/stream/movie",
                params={"tmdb_id": tmdb_id, "title": title},
                timeout=30,
            )
            if r.status_code == 200:
                data = r.json()
                print(f"Movie: {title}")
                print(f"  Stream URL: {'Found' if data.get('stream_url') else 'None'}")
                print(f"  Qualities: {len(data.get('qualities', []))}")
                print(f"  Downloads: {len(data.get('download_qualities', []))}")
            else:
                print(f"Movie: {title} -> Status {r.status_code}")
        except Exception as e:
            print(f"Error: {e}")

async def test_series(title, tmdb_id, season, episode):
    api_base = "http://localhost:8003/api"
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(
                f"{api_base}/stream/series",
                params={"tmdb_id": tmdb_id, "title": title, "season": season, "episode": episode},
                timeout=30,
            )
            if r.status_code == 200:
                data = r.json()
                print(f"Series: {title} S{season:02}E{episode:02}")
                print(f"  Stream URL: {'Found' if data.get('stream_url') else 'None'}")
                print(f"  Qualities: {len(data.get('qualities', []))}")
                print(f"  Downloads: {len(data.get('download_qualities', []))}")
            else:
                print(f"Series: {title} -> Status {r.status_code}")
        except Exception as e:
            print(f"Error: {e}")

async def main():
    await test_series("The Penguin", 111110, 1, 1)

if __name__ == "__main__":
    asyncio.run(main())
