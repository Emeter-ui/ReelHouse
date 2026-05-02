import asyncio
import sys
import os

sys.path.insert(0, 'c:/Users/Dave/Desktop/New folder (3)/backend')
from app.routes.stream import _resolve
from moviebox_api.v1.constants import SubjectType

async def main():
    res = await _resolve('Kung Fu Panda 4', 2024, SubjectType.MOVIES)
    print("Kung Fu Panda 4:", [{'res': q['resolution'], 'url': q['url']} for q in res['qualities']])

asyncio.run(main())
