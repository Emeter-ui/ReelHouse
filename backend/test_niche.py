import httpx
import asyncio
import json

async def test(title, tmdb_id):
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
                print(f"Title: {title}")
                print(f"  Stream URL: {'Found' if data.get('stream_url') else 'None'}")
                print(f"  Qualities: {len(data.get('qualities', []))}")
                print(f"  Downloads: {len(data.get('download_qualities', []))}")
            else:
                print(f"Title: {title} -> Status {r.status_code}")
        except Exception as e:
            print(f"Error: {e}")

async def main():
    # A Trip to the Moon
    await test("A Trip to the Moon", 775)
    # Something very new maybe?
    # await test("Sonic the Hedgehog 3", 939243) 

if __name__ == "__main__":
    asyncio.run(main())
