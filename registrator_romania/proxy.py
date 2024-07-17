from __future__ import annotations

from abc import ABC, abstractmethod
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
import re
import socket
import threading
import time
import traceback
from typing import TYPE_CHECKING, List, Literal, Type
from warnings import warn
import warnings
import aiohttp.client_exceptions
from loguru import logger

import aiofiles
import aiohttp
from aiohttp_socks import ProxyConnector
from fake_useragent import UserAgent
from flask import session
import ua_generator
from apscheduler.schedulers.background import BackgroundScheduler
import orjson

from registrator_romania import config

if TYPE_CHECKING:
    from types import FunctionType


AIOHTTP_NET_ERRORS = (
    aiohttp.client_exceptions.ContentTypeError,
    aiohttp.client_exceptions.ClientConnectionError,
    aiohttp.client_exceptions.ClientHttpProxyError,
    aiohttp.client_exceptions.ClientProxyConnectionError,
    aiohttp.client_exceptions.ClientResponseError,
    aiohttp.client_exceptions.ClientPayloadError,
    aiohttp.ClientOSError,
    aiohttp.ServerDisconnectedError,
    asyncio.TimeoutError,
)


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
    url = "https://api.ipify.org"

    connector = aiohttp.TCPConnector(loop=asyncio.get_running_loop())
    async with AiohttpSession().generate(
        close_connector=close_connector,
        connector=connector,
        total_timeout=timeout or 20,
    ) as session:
        
        try:
            start = datetime.datetime.now()
            async with session.get(url, proxy=proxy) as resp:
                result = (
                    await resp.text(),
                    proxy,
                    datetime.datetime.now() - start,
                )
                if queue:
                    await asyncio.to_thread(queue.put, result, block=False)
                return result
        except AIOHTTP_NET_ERRORS:
            return tuple()
        except UnicodeError:
            return tuple()
        except Exception as e:
            print(f"{e.__class__.__name__}: {e}")
            # logger.exception(e)
            return tuple()


class AiohttpSession:
    def generate_connector(self):
        return aiohttp.TCPConnector(
            # ssl=False,
            limit=0,
            limit_per_host=0,
            # force_close=False,
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
            # connector=connector,
            # json_serialize=orjson.dumps,
            # connector_owner=close_connector,
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


class AutomaticProxyPool:
    def __init__(
        self,
        proxies: list[str], 
        debug: bool = False,
        second_check: bool = False,
        sources_classes: list[Type] = None,
        second_check_url: str = None,
        second_check_headers: dict = None,
    ) -> None:
        self._scheduler = BackgroundScheduler()
        self._scheduler.add_job(self._add_new_proxies, "interval", minutes=10)
        self._scheduler.start()

        self._process: multiprocessing.Process = None
        self._queue = multiprocessing.Queue()
        self._event = multiprocessing.Event()
        self._pool = AiohttpSession().generate_connector()
        self._proxies = []
        self._proxies_reports = {}
        self.debug = debug
        self._append_pool_task: asyncio.Task = None
        self._src_proxies_list = proxies
        self._do_second_check = second_check
        self._timeout_proxies = {}
        self._last_proxy_used: str = None
        self._proxy_for = {
            "url": "",
            "headers": {},
            "best_proxy": "",
            "proxies": [],
        }
        self._lock = asyncio.Lock()
        self._urls: list[dict[str, dict[str, str]]] = {}
        # Example:
        # [{"https://url1.com": {"proxy": "https://proxy:8080", "timeout": 2}}]
        # timeout in seconds
        self._sources_cls = [] if not sources_classes else sources_classes
        self._second_check_url = second_check_url or "https://api.ipify.org"
        self._second_check_headers = second_check_headers or {"Accept": "*/*"}

    @property
    def last_proxy_used(self):
        return self._last_proxy_used

    def _add_new_proxies(self):
        async def add_new_proxies_async():
            proxies_classes = self._sources_cls or (
                GeoNode(),
                FreeProxies(),
                FreeProxiesList(),
                ImRavzanProxyList(),
                LionKingsProxy(),
                TheSpeedX(),
                ProxyMaster(),
            )
            for proxy_class in proxies_classes:
                try:
                    proxies = await proxy_class.list_socks5_proxy()
                except Exception:
                    continue
                else:
                    self._src_proxies_list.extend(
                        [
                            proxy
                            for proxy in proxies
                            if proxy not in self.proxies
                        ]
                    )

        loop = asyncio.new_event_loop()
        loop.run_until_complete(add_new_proxies_async())
        loop.close()

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
        self._scheduler.remove_all_jobs()
        del self._scheduler

    async def _append_pool(self):
        async def send_request(proxy: str):
            if proxy in self.proxies:
                return

            async with AiohttpSession().generate(
                connector=self._pool, total_timeout=4
            ) as session:
                session._default_headers = self._second_check_headers

                if self.debug:
                    logger.debug(f"append_pool: {proxy}")

                try:
                    if self._do_second_check:
                        start = datetime.datetime.now()
                        async with session.get(
                            self._second_check_url, proxy=proxy
                        ):
                            stop = datetime.datetime.now()
                            if self.debug:
                                logger.debug(
                                    "Second check was successfully: "
                                    f"{proxy} - {start - stop}"
                                )
                    self._proxies.append(proxy)
                    self.proxy_working(proxy)
                except AIOHTTP_NET_ERRORS:
                    pass
                except Exception as e:
                    logger.exception(e)

        async def background():
            try:
                while True:
                    tasks = []
                    async for proxy, time in self:
                        task = asyncio.create_task(send_request(proxy))
                        tasks.append(task)
                        await asyncio.sleep(0.250)

                    await asyncio.gather(*tasks)
                    self.start_background()
            except asyncio.CancelledError:
                print("Background task was cancelled")
                pass

        self._append_pool_task = asyncio.get_event_loop().create_task(
            background()
        )
        await asyncio.sleep(0.250)
        return self

    async def __anext__(self):
        while True:                 
            if self._event.is_set():
                raise StopAsyncIteration

            try:
                result = await asyncio.to_thread(self._queue.get_nowait)
            except queue.Empty:
                if self._event.is_set():
                    raise StopAsyncIteration

            except Exception:
                logger.critical(traceback.format_exc())

            else:
                if isinstance(result, tuple):
                    time = result[2]
                    proxy = result[1]
                    if self.debug:
                        logger.debug(f"__anext__(): return proxy - {proxy}")

                    return proxy, time

                if result == "finish":
                    raise StopAsyncIteration

    def restart_background(self):
        self.drop_background()
        self.start_background()

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
            divides = 700
            # proxies [0, 0, 0, 0, 0, 0]
            # divides: 2, chunks [[0, 0], [0, 0], [0, 0]]
            chunks = divide_list(proxies, divides=divides)

            for chunk in divide_list(chunks, divides=2):
                try:
                    with ThreadPoolExecutor(
                        max_workers=os.cpu_count() * 2
                    ) as e:
                        e.map(run_th, chunk, [q for _ in chunk])
                    time.sleep(3)
                except KeyboardInterrupt:
                    e.shutdown(wait=True, cancel_futures=True)

            event.set()
            q.put("finish")

        self._event.clear()
        self._process = multiprocessing.Process(
            target=run, args=(self._queue, self._src_proxies_list, self._event)
        )
        self._process.start()

    @property
    def proxies(self):
        return self._proxies

    def set_proxies_for_url(self, list_of_proxies: list[str]):
        self._proxy_for["proxies"] = list_of_proxies

    def sort_proxies_by_timeout(self, proxies: list[dict[str, str | int]]):
        filtered = list(sorted(proxies, key=lambda p: p["timeout"]))
        return filtered

    async def get_session(self, timeout: int = 5) -> aiohttp.ClientSession:
        if not self.proxies:
            raise ValueError("Proxies list empty")
        session = AiohttpSession().generate(
            # connector=self._pool, total_timeout=timeout
            total_timeout=timeout
        )
        self_class = self

        async def _request(*args, **kwargs):
            # Get proxy and url from parameters before do request
            proxy = kwargs.get("proxy")
            url = args[1]
            proxies = []
            set_ = None

            if not proxy:  # If bool(proxy) == False
                async with session._lock:
                    proxy = self_class.get_best_proxy_by_timeout()
                kwargs["proxy"] = proxy
                set_ = False

                async with session._lock:
                    if not self_class._urls.get(url):
                        # If we not have any proxies for this site, we are
                        # collect them
                        try:
                            proxies = await self_class.collect_valid_proxies(
                                url=url,
                                headers=session._default_headers,
                            )
                        except Exception as e:
                            logger.exception(e)

                        if proxies:
                            # Set the most speed proxy
                            set_ = True
                            proxies = self_class.sort_proxies_by_timeout(
                                proxies
                            )
                            proxy = proxies.pop(0)["proxy"]
                            self_class._urls[url] = proxies

                            kwargs["proxy"] = proxy

                    elif self_class._urls[url]:
                        set_ = True
                        proxy = self_class._urls[url].pop(0)["proxy"]
                        kwargs["proxy"] = proxy

            if self_class.debug and proxy:
                logger.debug(f"Do request on {url} with proxy {proxy}")

            if proxy:
                async with session._lock:
                    tsk = asyncio.current_task()
                    msg = f", task - {tsk.get_name()}" if tsk else ""
                    # print(f"{proxy}, set for url: {set_}{msg}")
                    self_class._last_proxy_used = proxy

            start = datetime.datetime.now()
            try:
                # async with asyncio.Semaphore(8):
                result = await session._request_(*args, **kwargs)
                stop = datetime.datetime.now()

                if proxy:
                    self_class._timeout_proxies[proxy] = stop - start

                    if url not in self_class._urls:
                        self_class._urls[url] = []
                    try:
                        list_proxies_for_url = self_class._urls[url].copy()
                        proxy_record = [
                            record
                            for record in list_proxies_for_url
                            if record["proxy"] == proxy
                        ]

                        if not proxy_record:
                            proxy_record = {
                                "proxy": proxy,
                                "timeout": (stop - start).microseconds,
                            }
                            list_proxies_for_url.append(proxy_record)
                            i = -1
                        else:
                            proxy_record = proxy_record[0]
                            i = list_proxies_for_url.index(proxy_record)

                        list_proxies_for_url[i] = {
                            "proxy": proxy,
                            "timeout": (stop - start).microseconds,
                        }
                        new_list = self_class.sort_proxies_by_timeout(
                            proxies=list_proxies_for_url
                        )
                        async with session._lock:
                            self_class._urls[url] = new_list
                    except (ValueError, ValueError):
                        pass

                if proxy and result.status != 200:
                    self_class.proxy_not_working(proxy=proxy)
                elif proxy and proxy in self_class.proxies:
                    self_class.proxy_working(proxy=proxy)

                return result
            except AIOHTTP_NET_ERRORS as e:
                if proxy and proxy in self_class.proxies:
                    self_class.proxy_not_working(proxy=proxy)
                    if self_class._timeout_proxies.get(proxy):
                        del self_class._timeout_proxies[proxy]

                if url in self_class._urls:
                    async with session._lock:
                        proxy_record = [
                            record
                            for record in self_class._urls[url]
                            if record["proxy"] == proxy
                        ]

                        if proxy_record:
                            i = self_class._urls[url].index(proxy_record[0])
                            del self_class._urls[url][i]

                raise e
            finally:
                if session._lock.locked():
                    session._lock.release()

        session._request_ = session._request
        session._request = _request
        session._lock = asyncio.Lock()

        return session

    async def collect_valid_proxies(self, url: str, headers: dict[str, str]):
        session = AiohttpSession().generate(
            connector=self._pool, close_connector=False, total_timeout=4
        )
        session._default_headers = headers

        proxies = self.proxies

        async def send_req(proxy: str):
            start = datetime.datetime.now()
            try:
                async with session.get(url, proxy=proxy) as resp:
                    await resp.text()
                    if resp.status == 200:
                        return True, proxy, datetime.datetime.now() - start
            except Exception as e:
                return False, proxy

        async with session:
            results = await asyncio.gather(
                *[send_req(proxy) for proxy in proxies]
            )
        proxies = [
            (result[1], result[2]) for result in results if result and result[0]
        ]
        return [
            {"proxy": proxy[0], "timeout": proxy[1].microseconds}
            for proxy in sorted(proxies, key=lambda part: part[1])
        ]

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
        if proxy not in self.proxies:
            return
        if not self._proxies_reports.get(proxy):
            self._proxies_reports[proxy] = 0
            return

        self._proxies_reports[proxy] -= 1

        if self._proxies_reports[proxy] < 0:
            self._proxies_reports[proxy] = 0

    def get_best_proxy(self):
        if not self._proxies_reports:
            return random.choice(self.proxies)
        proxies_stats = list(self._proxies_reports.copy().items())
        random.shuffle(proxies_stats)
        return min(proxies_stats, key=lambda x: x[1])[0]

    def get_best_proxy_by_timeout(self):
        if not self._timeout_proxies:
            return self.get_best_proxy()
        proxies_stats = list(self._timeout_proxies.copy().items())
        random.shuffle(proxies_stats)
        return min(proxies_stats, key=lambda x: x[1])[0]


def divide_list(src_list: list, divides: int = 100):
    return [src_list[x : x + divides] for x in range(0, len(src_list), divides)]


async def filter_proxies(proxies: list[str], debug: bool = False):
    f = AutomaticProxyPool(proxies, debug=debug, second_check=True)
    await f
    return f


class AnyProxy:
    async def list_http_proxy(self):
        return []

    async def list_socks4_proxy(self):
        return []

    async def list_socks5_proxy(self):
        return []


class ProxyMaster(AnyProxy):
    """
    Github - https://github.com/MuRongPIG/Proxy-Master
    """

    async def list_http_proxy(self) -> list[str]:
        url = "https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/http.txt"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                proxies = await resp.text()
                return [f"http://{p.strip()}" for p in proxies.splitlines()]

    async def list_socks4_proxy(self) -> list[str]:
        url = "https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/socks4.txt"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                proxies = await resp.text()
                return [f"socks4://{p.strip()}" for p in proxies.splitlines()]

    async def list_socks5_proxy(self) -> list[str]:
        url = "https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/socks5.txt"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                proxies = await resp.text()
                return [f"socks5://{p.strip()}" for p in proxies.splitlines()]


class FreeProxies(AnyProxy):
    """
    Github - https://github.com/Anonym0usWork1221/Free-Proxies
    """

    async def list_http_proxy(self) -> list[str]:
        url = "https://raw.githubusercontent.com/Anonym0usWork1221/Free-Proxies/main/proxy_files/http_proxies.txt"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                proxies = await resp.text()
                return [f"http://{p.strip()}" for p in proxies.splitlines()]

    async def list_socks4_proxy(self) -> list[str]:
        url = "https://raw.githubusercontent.com/Anonym0usWork1221/Free-Proxies/main/proxy_files/socks4_proxies.txt"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                proxies = await resp.text()
                return [f"socks4://{p.strip()}" for p in proxies.splitlines()]

    async def list_socks5_proxy(self) -> list[str]:
        url = "https://raw.githubusercontent.com/Anonym0usWork1221/Free-Proxies/main/proxy_files/socks5_proxies.txt"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                proxies = await resp.text()
                return [f"socks5://{p.strip()}" for p in proxies.splitlines()]


class FreeProxiesList(AnyProxy):
    """
    GitHub - https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/http.txt
    """

    async def list_http_proxy(self) -> list[str]:
        url = "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/http.txt"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                proxies = await resp.text()
                return [f"http://{p.strip()}" for p in proxies.splitlines()]

    async def list_socks4_proxy(self) -> list[str]:
        url = "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/socks4.txt"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                proxies = await resp.text()
                return [f"socks4://{p.strip()}" for p in proxies.splitlines()]

    async def list_socks5_proxy(self) -> list[str]:
        url = "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/socks5.txt"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                proxies = await resp.text()
                return [f"socks5://{p.strip()}" for p in proxies.splitlines()]


class GeoNode(AnyProxy):
    async def list_http_proxy(self) -> list[str]:
        url = "https://proxylist.geonode.com/api/proxy-list?protocols=http&limit=500&sort_by=lastChecked&sort_type=desc"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                response = await resp.json()
                return [
                    f"http://{obj["ip"]}:{obj["port"]}"
                    for obj in response["data"]
                ]

    async def list_socks4_proxy(self) -> list[str]:
        url = "https://proxylist.geonode.com/api/proxy-list?protocols=socks4&limit=500&sort_by=lastChecked&sort_type=desc"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                response = await resp.json()
                return [
                    f"socks4://{obj["ip"]}:{obj["port"]}"
                    for obj in response["data"]
                ]

    async def list_socks5_proxy(self) -> list[str]:
        url = "https://proxylist.geonode.com/api/proxy-list?protocols=socks5&limit=500&sort_by=lastChecked&sort_type=desc"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                response = await resp.json()
                return [
                    f"socks5://{obj["ip"]}:{obj["port"]}"
                    for obj in response["data"]
                ]


class ImRavzanProxyList(AnyProxy):
    """
    https://raw.githubusercontent.com/im-razvan/proxy_list/main/http.txt
    """

    async def list_http_proxy(self):
        url = "https://raw.githubusercontent.com/im-razvan/proxy_list/main/http.txt"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                proxies = await resp.text()
                return [f"http://{p.strip()}" for p in proxies.splitlines()]

    async def list_socks4_proxy(self) -> list:
        return []

    async def list_socks5_proxy(self) -> list[str]:
        url = "https://raw.githubusercontent.com/im-razvan/proxy_list/main/socks5.txt"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                proxies = await resp.text()
                return [f"socks5://{p.strip()}" for p in proxies.splitlines()]


class LionKingsProxy(AnyProxy):
    """
    https://raw.githubusercontent.com/saisuiu/Lionkings-Http-Proxys-Proxies/main/free.txt
    """

    async def list_http_proxy(self):
        url = "https://raw.githubusercontent.com/saisuiu/Lionkings-Http-Proxys-Proxies/main/free.txt"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                proxies = await resp.text()
                return [
                    f"http://{p.strip()}"
                    for p in proxies.splitlines()
                    if is_host_port(p.strip())
                ]


class TheSpeedX:
    """
    https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt
    """

    async def list_http_proxy(self):
        url = "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt"
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


async def get_ip(session: aiohttp.ClientSession, proxy=None, hd: dict = None):
    url = "https://api.ipify.org"
    url = "https://ipinfo.io/ip"
    # url = "https://programarecetatenie.eu/programare_online"
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
        "Connection": "keep-alive",
    }
    for k, v in ua_generator.generate().headers.get().items():
        headers[k] = v

    if hd:
        headers = hd
    session._default_headers = headers
    try:
        async with session.get(url) as resp:
            return await resp.text()
    except AIOHTTP_NET_ERRORS:
        pass
    except Exception as e:
        logger.exception(e)
        print(f"{e.__class__.__name__}: {e}")
        pass


async def main():
    proxies_classes = (
        # GeoNode(),
        # FreeProxies(),
        FreeProxiesList(),
        ImRavzanProxyList(),
        LionKingsProxy(),
        # ProxyMaster(),
        # TheSpeedX(),
    )

    proxies = [
        proxy
        for cls in proxies_classes
        for proxy in await cls.list_http_proxy()
    ]

    url = "https://programarecetatenie.eu/programare_online"
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }
    for k, v in ua_generator.generate().headers.get().items():
        headers[k] = v

    print(f"Raw proxies: {len(proxies)}")

    pool = await AutomaticProxyPool(
        proxies=proxies,
        second_check=False,
    )
    works_proxy = 0
    proxies = []
    with open("auto-proxy.txt", "w") as f:
        f.write(f"SESSION WITH URL: {url}\n")
    while True:
        if len(pool.proxies) < 10:
            await asyncio.sleep(1)
            continue
        await asyncio.sleep(1.5)

        print(f"We have total {len(pool.proxies)} proxies")
        
        start = datetime.datetime.now()
        session = await pool.get_session()
        async with session:
            start = datetime.datetime.now()
            res = await asyncio.gather(
                *[get_ip(session, None, headers) for _ in range(60)]
            )
            # pprint(res)
            print(
                f"{len(res)} requests "
                f"({len([r for r in res if not r])} failed) in "
                f"{datetime.datetime.now() - start}."
            )
            continue
            # return
            # stop = datetime.datetime.now()
            # if res:
            #     result = f"Successfully"
            # else:
            #     result = f"Failed"

            # msg = f"auto proxy: {result}. Timeout: {stop - start}"
            # print(msg)

            # async with aiofiles.open("auto-proxy.txt", "a") as f:
            #     await f.write(f"{msg}\n")

        continue
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
            f"\nwork only {works_num} proxies\n\n",
        )


if __name__ == "__main__":
    asyncio.run(main())
