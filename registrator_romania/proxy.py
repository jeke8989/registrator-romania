from __future__ import annotations

import asyncio
import json
import random
from functools import wraps
from typing import TYPE_CHECKING, List
from venv import logger

import aiohttp
from aiohttp_socks import ProxyConnector
from fake_useragent import UserAgent

if TYPE_CHECKING:
    from types import FunctionType


def aiohttp_session(
    timeout: int = 5, attempts: int = 5, sleeps: tuple[int, int] = (2, 5)
):
    def wrapper(f: FunctionType):
        @wraps(f)
        async def inner(*args, **kwargs):
            nonlocal attempts
            connector = aiohttp.TCPConnector(ssl=False, limit_per_host=10)
            headers = {"User-Agent": UserAgent().random}
            client_timeout = aiohttp.ClientTimeout(total=timeout)

            async with aiohttp.ClientSession(
                connector=connector,
                trust_env=True,
                timeout=client_timeout,
                headers=headers,
            ) as session:
                try:
                    return await f(session, *args, **kwargs)
                except asyncio.TimeoutError:
                    if attempts:
                        attempts = -1
                        await asyncio.sleep(random.uniform(*sleeps))
                        return await inner(*args, **kwargs)
                    raise
                finally:
                    if not session.closed:
                        await session.close()

        return inner

    return wrapper


@aiohttp_session(timeout=7)
async def get_proxies(session: aiohttp.ClientSession) -> List[str]:
    key = "8170de9bb395804d366354100e99271b"
    url = (
        "http://api.best-proxies.ru/proxylist.txt?"
        f"key={key}&includeType=1&type=http&type=https&level=1"
    )
    async with session.get(url) as resp:
        response = await resp.text()
        return response.splitlines()


@aiohttp_session(timeout=7, attempts=3)
async def check_proxy(session: aiohttp.ClientSession, proxy: str) -> dict:
    url = "https://api.ipify.org?format=json"
    try:
        async with session.get(url, proxy=proxy) as resp:
            return await resp.json()
    except Exception as e:
        logger.exception(e)
        return {}
