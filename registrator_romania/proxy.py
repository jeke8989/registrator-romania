from __future__ import annotations

import asyncio
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import datetime
import json
import multiprocessing
import os
from pprint import pprint
import queue
import random
from functools import wraps
import socket
import threading
import traceback
from typing import TYPE_CHECKING, List, Literal
import aiohttp.client_exceptions
from loguru import logger

import aiofiles
import aiohttp
from aiohttp_socks import ProxyConnector
from fake_useragent import UserAgent
from flask import session
import ua_generator
import orjson

from registrator_romania import config

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


async def check_proxy(
    proxy: str,
    queue: multiprocessing.Queue = None,
    connector: aiohttp.TCPConnector = None,
    timeout: int = None,
    close_connector: bool = False,
) -> dict:
    url = "https://api.ipify.org?format=json"

    net_errors = (
        aiohttp.ClientProxyConnectionError,
        aiohttp.ClientConnectionError,
        aiohttp.ServerDisconnectedError,
        aiohttp.ClientHttpProxyError,
        aiohttp.ClientOSError,
        asyncio.TimeoutError,
    )

    async with AiohttpSession().generate(
        close_connector=close_connector,
        connector=connector,
        total_timeout=timeout or 300,
    ) as session:
        try:
            start = datetime.datetime.now()
            async with session.get(url, proxy=proxy) as resp:
                ...
                result = (
                    await resp.json(),
                    proxy,
                    datetime.datetime.now() - start,
                )
                if queue:
                    await asyncio.to_thread(queue.put, result, block=False)
                return result
        except net_errors:
            return tuple()
        except Exception as e:
            print(f"{e.__class__.__name__}: {e}")
            # logger.exception(e)
            return tuple()


class AiohttpSession:
    def __init__(self) -> None:
        pass

    def generate_connector(self):
        return aiohttp.TCPConnector(
            ssl=False,
            limit=None,
            limit_per_host=0,
            force_close=False,
        )

    def generate(
        self,
        connector: aiohttp.TCPConnector = None,
        close_connector: bool = False,
        total_timeout: int = 5,
    ):
        if connector is None:
            connector = self.generate_connector()

        timeout = aiohttp.ClientTimeout(total_timeout)
        session = aiohttp.ClientSession(
            trust_env=True,
            connector=connector,
            json_serialize=orjson.dumps,
            connector_owner=close_connector,
            timeout=timeout,
        )
        return session


def run_th(proxies: list[str], q: multiprocessing.Queue):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    tasks = [check_proxy(p, queue=q, close_connector=True) for p in proxies]
    loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
    loop.close()


class FilterProxies:
    def __init__(
        self,
        pr: multiprocessing.Process,
        q: multiprocessing.Queue,
        e: multiprocessing.Event,
        debug: bool = False,
    ) -> None:
        self._process = pr
        self._queue = q
        self._event = e
        self._pool = AiohttpSession().generate_connector()
        self._proxies = []
        self._proxies_reports = {}
        self.debug = debug

    def __aiter__(self):
        return self

    def __await__(self):
        return self._append_pool().__await__()
    
    def __del__(self):
        print(
            "Unstopped background proccess filter "
            f"proxies: {self._process.name}. Stopping at now..."
        )
        self.drop_background()

    async def _append_pool(self):
        async def send_request(proxy: str):
            net_errors = (
                aiohttp.ClientProxyConnectionError,
                aiohttp.ClientConnectionError,
                aiohttp.ServerDisconnectedError,
                aiohttp.ClientHttpProxyError,
                aiohttp.ClientOSError,
                asyncio.TimeoutError,
            )
            
            async with AiohttpSession().generate(
                connector=self._pool, total_timeout=7
            ) as session:
                if self.debug:
                    logger.debug(f"append_pool: {proxy}")
                start = datetime.datetime.now()
                try:
                    async with session.get(
                        "https://api.ipify.org", proxy=proxy
                    ):
                        stop = datetime.datetime.now()
                        if self.debug:
                            logger.debug(f"Second check was successfully: {proxy} - {start - stop}")
                    self._proxies.append(proxy)
                except net_errors:
                    pass
                except Exception as e:
                    print(e)

        async def background():
            while True:
                tasks = []
                async for proxy, time in self:
                    if proxy in self.proxies:
                        continue
                    tasks.append(asyncio.create_task(send_request(proxy)))

                await asyncio.gather(*tasks)

        asyncio.get_event_loop().create_task(background())

    async def __anext__(self):
        q = self._queue

        if self._event.is_set() and q.empty():
            if self.debug:
                logger.debug("StopAsyncIteration")
            q.close()

            del self._queue
            del self._process

            raise StopAsyncIteration

        try:
            result = await asyncio.to_thread(q.get)
        except Exception as e:
            logger.critical(traceback.format_exc(e))
        else:
            if isinstance(result, tuple):
                time = result[2]
                proxy = result[1]
                if self.debug:
                    logger.debug(f"__anext__: {proxy}")

                return proxy, time

    async def __aenter__(self):
        return self

    def drop_background(self):
        self._event.set()

        self._process.kill()
        self._process.terminate()
        self._queue.close()

        del self._queue
        del self._process

    async def __aexit__(self, *args, **kwargs):
        return

    @property
    def proxies(self):
        return self._proxies

    async def get_session(
        self, timeout: int = 5
    ) -> tuple[aiohttp.ClientSession, list[str]]:
        if not self.proxies:
            raise ValueError("Proxies list empty")
        session = AiohttpSession().generate(
            connector=self._pool, total_timeout=timeout
        )
        self_class = self
  
        async def _request(*args, **kwargs):
            proxy_exceptions = (
                aiohttp.ClientProxyConnectionError,
                aiohttp.client_exceptions.ContentTypeError,
                aiohttp.client_exceptions.ClientConnectionError,
                aiohttp.client_exceptions.ClientHttpProxyError,
                aiohttp.client_exceptions.ClientProxyConnectionError,
                aiohttp.client_exceptions.ClientResponseError,
                asyncio.TimeoutError
            )
            proxy = kwargs.get("proxy")
            url = args[1]
            
            if self_class.debug and proxy:
                logger.debug(f"Do request on {url} with proxy {proxy}")
                
            try:
                result = await session._request_(*args, **kwargs)
                status = result.status
                
                if status != 200:
                    self_class.proxy_not_working(proxy=proxy)
                elif proxy and proxy in self_class.proxies:
                    self_class.proxy_working(proxy=proxy)
                    
                return result
            except proxy_exceptions as e:
                if proxy and proxy in self_class.proxies:
                    self_class.proxy_not_working(proxy=proxy)
                raise e
        
        session._request_ = session._request
        session._request = _request
        
        return session, self.proxies

    def proxy_not_working(self, proxy: str):
        if proxy not in self.proxies:
            return

        if not self._proxies_reports.get(proxy):
            self._proxies_reports[proxy] = 0

        self._proxies_reports[proxy] += 1

        if self._proxies_reports[proxy] >= 3:
            del self._proxies_reports[proxy]
            self._proxies.remove(proxy)

    def proxy_working(self, proxy: str):
        if proxy not in self.proxies or not self._proxies_reports.get(proxy):
            return

        self._proxies_reports[proxy] -= 1

        if self._proxies_reports[proxy] == 0:
            del self._proxies_reports[proxy]


def divide_list(src_list: list, divides: int = 100):
    return [
        src_list[x : x + divides] for x in range(0, len(src_list), divides)
    ]


async def filter_proxies(proxies: list[str], debug: bool = False):
    q = multiprocessing.Queue()
    event = multiprocessing.Event()

    def run(
        q: multiprocessing.Queue,
        proxies: list[str],
        event: multiprocessing.Event,
    ):
        divides = 1000
        chunks = divide_list(proxies, divides=divides)

        with ThreadPoolExecutor(max_workers=os.cpu_count() ** 2) as e:
            e.map(run_th, chunks, [q for _ in chunks])

        event.set()

    pr = multiprocessing.Process(target=run, args=(q, proxies, event))
    pr.start()

    f = FilterProxies(pr, q, event, debug=debug)
    await f
    return f


class Proxysio:
    """
    Documentation - https://proxys.io/ru/api/v2/doc
    """

    def __init__(self) -> None:
        cfg = config.get_config()
        self._api_key = cfg["proxysio"]["api_key"]
        self._base_url = "https://proxys.io/ru/api/v2"

    async def list_proxy(
        self, scheme: Literal["http", "https"] = "http"
    ) -> list[str]:
        url = self._base_url + f"/ip?key={self._api_key}"

        @aiohttp_session()
        async def request(session: aiohttp.ClientSession):
            resp = await session.get(url)
            return await resp.json()

        # response = await request()
        response = ["http://tBO8tjSZXj:M64o9nRlGo@65.21.25.28:1033"]
        logger.debug(f"Proxysio list_proxy: \n{response}")
        return response
        # _key = f"port_{scheme}"
        # user = response["data"][0]["username"]
        # password = response["data"][0]["password"]
        # return [
        #     f"{scheme}://{user}:{password}@{obj["ip"]}:{obj[_key]}"
        #     for obj in response["data"][0]["list_ip"]
        # ]


class ProxyMaster:
    """
    Github - https://github.com/MuRongPIG/Proxy-Master
    """

    async def list_proxy(self) -> list[str]:
        url = "https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/http.txt"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                proxies = await resp.text()
                return [f"http://{p.strip()}" for p in proxies.splitlines()]


class FreeProxies:
    """
    Github - https://github.com/Anonym0usWork1221/Free-Proxies
    """

    async def list_proxy(self) -> list[str]:
        url = "https://raw.githubusercontent.com/Anonym0usWork1221/Free-Proxies/main/proxy_files/http_proxies.txt"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                proxies = await resp.text()
                return [f"http://{p.strip()}" for p in proxies.splitlines()]


class GeoNode:
    async def list_proxy(self) -> list[str]:
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
            "if-none-match": 'W/"b639-iIGkdAHjH3G4RBuh+yrCCEnidm4"',
            "origin": "https://geonode.com",
            "priority": "u=1, i",
            "referer": "https://geonode.com/",
        }

        ua = ua_generator.generate().headers.get()

        for k, v in ua.items():
            headers[k] = v

        url = "https://proxylist.geonode.com/api/proxy-list?protocols=http&limit=500&sort_by=lastChecked&sort_type=desc"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                response = await resp.json()
                return [
                    f"http://{obj["ip"]}:{obj["port"]}"
                    for obj in response["data"]
                ]


async def main():
    p = ProxyMaster()
    proxies = await p.list_proxy()
    # proxies = proxies + await FreeProxies().list_proxy()
    p = GeoNode()
    proxies = await p.list_proxy() + await FreeProxies().list_proxy()
    print(f"Raw proxies: {len(proxies)}")

    filtered = await filter_proxies(proxies)
    while True:
        await asyncio.sleep(2)
        pprint(filtered.proxies)
        if not filtered.proxies:
            continue

        session, proxies = await filtered.get_session()
        proxy = random.choice(proxies)
        try:
            async with session:
                async with session.get(
                    "https://icanhazip.com", proxy=proxy
                ) as resp:
                    logger.success(f"Proxy {proxy}:", await resp.text())
                    filtered.proxy_working(proxy)
        except Exception as e:
            logger.warning(
                f"icanhazip.com: {e}. proxy {proxy} not working", flush=True
            )
            filtered.proxy_not_working(proxy)


if __name__ == "__main__":
    asyncio.run(main())
