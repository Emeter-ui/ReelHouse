import httpx
import asyncio

_PLAY_DOMAIN_DISCOVERY = (
    "https://h5-api.aoneroom.com/wefeed-h5api-bff/media-player/get-domain"
)
_PLAY_DOMAIN_FALLBACK = "https://h5.aoneroom.com"
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_X_CLIENT_INFO = '{"timezone":"Africa/Nairobi"}'

async def main():
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(
                _PLAY_DOMAIN_DISCOVERY,
                headers={
                    "User-Agent": _BROWSER_UA,
                    "Accept": "application/json",
                    "X-Client-Info": _X_CLIENT_INFO,
                    "X-Client-Type": "h5",
                },
                timeout=5,
            )
            print(f"Status: {r.status_code}")
            print(f"Response: {r.text}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
