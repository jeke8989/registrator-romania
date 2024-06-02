from __future__ import annotations

import asyncio
import random
from functools import wraps
from typing import TYPE_CHECKING

import aiohttp
from fake_useragent import UserAgent
from proxybroker import Broker

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


@aiohttp_session()
async def main(session: aiohttp.ClientSession, q: asyncio.Queue):
    URL = r"https://api.ipify.org?format=json"
    proxy = "http://162.223.94.164:80"
    while True:
        proxy = await q.get()
        if proxy is None:
            continue
        proto = "https" if "HTTPS" in proxy.types else "http"
        row = "%s://%s:%d\n" % (proto, proxy.host, proxy.port)
        print(row)
        async with session.get(URL, proxy=row) as response:
            print(await response.json())


if __name__ == "__main__":
    q = asyncio.Queue()
    broker = Broker(q)
    task = asyncio.gather(
        broker.find(types=["HTTP", "HTTPS"], limit=10), main(q)
    )
    loop = asyncio.get_event_loop()
    loop.run_until_complete(task)
