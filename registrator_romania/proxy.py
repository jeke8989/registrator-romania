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
import re
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
        aiohttp.ClientResponseError,
        aiohttp.ClientHttpProxyError,
        aiohttp.ClientOSError,
        asyncio.TimeoutError,
    )

    async with AiohttpSession().generate(
        close_connector=close_connector,
        connector=connector,
        total_timeout=timeout or 20,
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
        except UnicodeError:
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
            limit=0,
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
    results = loop.run_until_complete(
        asyncio.gather(*tasks, return_exceptions=True)
    )
    loop.close()
    return results


class FilterProxies:
    def __init__(self, proxies: list[str], debug: bool = False) -> None:
        self._process: multiprocessing.Process = None
        self._queue = multiprocessing.Queue()
        self._event = multiprocessing.Event()
        self._pool = AiohttpSession().generate_connector()
        self._proxies = []
        self._proxies_reports = {}
        self.debug = debug
        self._append_pool_task: asyncio.Task = None
        self._src_proxies_list = proxies

    def __aiter__(self):
        return self

    def __await__(self):
        self.start_background()
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
                aiohttp.ClientResponseError,
                asyncio.TimeoutError,
            )

            if proxy in self.proxies:
                return

            async with AiohttpSession().generate(
                connector=self._pool, total_timeout=7
            ) as session:
                if self.debug:
                    logger.debug(f"append_pool: {proxy}")
                start = datetime.datetime.now()
                try:
                    # async with session.get(
                    #     "https://api.ipify.org", proxy=proxy
                    # ):
                    #     stop = datetime.datetime.now()
                    #     if self.debug:
                    #         logger.debug(
                    #             f"Second check was successfully: {proxy} - {start - stop}"
                    #         )
                    self._proxies.append(proxy)
                except net_errors:
                    pass
                except Exception as e:
                    print(f"{e.__class__.__name__}: {e}")

        async def background():
            try:
                while True:
                    tasks = []
                    async for proxy, time in self:
                        tasks.append(asyncio.create_task(send_request(proxy)))

                    await asyncio.gather(*tasks)
                    self.start_background()
            except asyncio.CancelledError:
                print("Background task was cancelled")
                pass

        self._append_pool_task = asyncio.get_event_loop().create_task(
            background()
        )

    async def __anext__(self):
        q = self._queue

        def stop():
            if self.debug:
                logger.debug("StopAsyncIteration")
            raise StopAsyncIteration

        while True:
            if self._event.is_set():
                stop()
                raise StopAsyncIteration

            try:
                result = await asyncio.to_thread(q.get, timeout=5)
            except queue.Empty:
                if self._event.is_set():
                    stop()
                    raise StopAsyncIteration

            except Exception as e:
                logger.critical(traceback.format_exc(e))

            else:
                if isinstance(result, tuple):
                    time = result[2]
                    proxy = result[1]
                    if self.debug:
                        logger.debug(f"__anext__: {proxy}")

                    return proxy, time

                if result == "finish":
                    stop()
                    raise StopAsyncIteration

    async def __aenter__(self):
        return self

    def restart_background(self):
        self.drop_background()
        self.start_background()

    def drop_background(self):
        if self._process:
            if self._process.is_alive():
                self._process.kill()
            self._process.close()
        if self._queue:
            self._queue.close()

        del self._queue
        del self._process
        self._queue = multiprocessing.Queue()
        self._process = None

    def start_background(self):
        def run(
            q: multiprocessing.Queue,
            proxies: list[str],
            event: multiprocessing.Event,
        ):
            # proxies = proxies[:500]
            divides = 1500
            # proxies [0, 0, 0, 0, 0, 0]
            # divides: 2, chunks [[0, 0], [0, 0], [0, 0]]
            chunks = divide_list(proxies, divides=divides)
            
            for chunk in divide_list(chunks, divides=2):
                with ThreadPoolExecutor(max_workers=os.cpu_count() ** 2) as e:
                    e.map(run_th, chunk, [q for _ in chunk])

            # with ThreadPoolExecutor(max_workers=os.cpu_count() ** 2) as e:
            #     e.map(run_th, chunks, [q for _ in chunks])

            event.set()
            q.put("finish")

        self._event.clear()
        self._process = multiprocessing.Process(
            target=run, args=(self._queue, self._src_proxies_list, self._event)
        )
        self._process.start()

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
                asyncio.TimeoutError,
            )
            proxy = kwargs.get("proxy")
            url = args[1]

            if self_class.debug and proxy:
                logger.debug(f"Do request on {url} with proxy {proxy}")

            try:
                result = await session._request_(*args, **kwargs)
                status = result.status

                if proxy and status != 200:
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

        if self._proxies_reports[proxy] >= 30:
            del self._proxies_reports[proxy]
            self._proxies.remove(proxy)

    def proxy_working(self, proxy: str):
        if proxy not in self.proxies or not self._proxies_reports.get(proxy):
            return

        self._proxies_reports[proxy] -= 1

        if self._proxies_reports[proxy] == 0:
            del self._proxies_reports[proxy]


def divide_list(src_list: list, divides: int = 100):
    return [src_list[x : x + divides] for x in range(0, len(src_list), divides)]


async def filter_proxies(proxies: list[str], debug: bool = False):
    q = multiprocessing.Queue()
    event = multiprocessing.Event()

    # def run(
    #     q: multiprocessing.Queue,
    #     proxies: list[str],
    #     event: multiprocessing.Event,
    # ):
    #     divides = 1500
    #     chunks = divide_list(proxies, divides=divides)

    #     with ThreadPoolExecutor(max_workers=os.cpu_count() ** 2) as e:
    #         e.map(run_th, chunks, [q for _ in chunks])

    #     event.set()

    # pr = multiprocessing.Process(target=run, args=(q, proxies, event))
    # pr.start()

    f = FilterProxies(proxies, debug=debug)
    await f
    return f


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


class FreeProxiesList:
    """
    GitHub - https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/http.txt
    """

    async def list_proxy(self) -> list[str]:
        url = "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/http.txt"
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


class ImRavzanProxyList:
    """
    https://raw.githubusercontent.com/im-razvan/proxy_list/main/http.txt
    """

    async def list_proxy(self):
        url = "https://raw.githubusercontent.com/im-razvan/proxy_list/main/http.txt"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                proxies = await resp.text()
                return [f"http://{p.strip()}" for p in proxies.splitlines()]


class LionKingsProxy:
    """
    https://raw.githubusercontent.com/saisuiu/Lionkings-Http-Proxys-Proxies/main/free.txt
    """

    async def list_proxy(self):
        url = "https://raw.githubusercontent.com/saisuiu/Lionkings-Http-Proxys-Proxies/main/free.txt"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                proxies = await resp.text()
                return [
                    f"http://{p.strip()}"
                    for p in proxies.splitlines()
                    if is_host_port(p.strip())
                ]


def is_host_port(v: str):
    if re.findall(r"\d+:\d+", v):
        return True


async def get_ip(session: aiohttp.ClientSession, proxy=None):
    try:
        async with session.get("https://api.ipify.org", proxy=proxy) as resp:
            return await resp.text()
    except Exception:
        pass


async def main():
    proxies = (
        await GeoNode().list_proxy()
        + await FreeProxies().list_proxy()
        + await FreeProxiesList().list_proxy()
        + await ImRavzanProxyList().list_proxy()
        + await LionKingsProxy().list_proxy()
        + await ProxyMaster().list_proxy()
    )

    print(f"Raw proxies: {len(proxies)}")

    pool = await filter_proxies(proxies, debug=False)
    works_proxy = 0

    while True:
        print(f"\n\nWe have {len(pool.proxies)} proxies")
        if not pool.proxies:
            await asyncio.sleep(2)
            continue

        session, proxies = await pool.get_session()
        async with session:
            start = datetime.datetime.now()

            res = await asyncio.gather(
                *[get_ip(session, proxy) for proxy in proxies]
            )
            stop = datetime.datetime.now()
            works_num = len(list(filter(None, res)))
            if works_num > works_proxy:
                works_proxy = works_num
                percents = works_num / len(pool.proxies) * 100
                with open("statistic-large.txt", "a") as f:
                    f.write(
                        f"{datetime.datetime.now()} "
                        f"Works {works_num} proxy. "
                        f"Total - {len(pool.proxies)} proxies. "
                        f"Working {percents}%"
                        f"Requests was send at {stop-start}\n"
                    )

            print(
                stop - start,
                f"\nwork only {works_num} proxies",
            )


if __name__ == "__main__":
    asyncio.run(main())
