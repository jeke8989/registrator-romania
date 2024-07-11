import asyncio
from datetime import date, datetime
import json
from os import device_encoding
from pprint import pprint

import random
import string
import traceback
import aiohttp
import aiohttp.client_exceptions
import dateutil
import dateutil.parser
from loguru import logger
from fake_useragent import UserAgent
import requests
from requests_toolbelt import MultipartEncoder
import urllib3
import ua_generator
from registrator_romania.proxy import (
    FreeProxies,
    GeoNode,
    divide_list,
    filter_proxies,
)

from registrator_romania.new_request_registrator import get_users_data_from_xslx
from registrator_romania.proxy import AiohttpSession


async def get_free_dates(
    session: aiohttp.ClientSession,
    month: int,
    tip_formular: int,
    proxy: str = None,
):
    month = f"0{month}" if len(str(month)) == 1 else str(month)
    headers = {
        "Accept": "*/*",
        "Referer": "https://programarecetatenie.eu/programare_online",
        "X-Requested-With": "XMLHttpRequest",
    }

    for k, v in ua_generator.generate().headers.get().items():
        headers[k] = v

    session._default_headers = headers
    session._json_serialize = json.dumps

    raw_payload = {
        "azi": f"{datetime.now().year}-{month}",
        "tip_formular": str(tip_formular),
    }

    url = "https://programarecetatenie.eu/status_zile"

    try:
        form = aiohttp.FormData()
        for k, v in raw_payload.items():
            form.add_field(k, v)

        async with session.post(url, data=form, proxy=proxy) as resp:
            resp.raise_for_status()
            raw_response = await resp.content.read()
            response = await resp.json(content_type=None)
            if not response and raw_response:
                response = json.loads(raw_response.decode())

        if not isinstance(response, dict) or not response.get("data"):
            return []

        dates_raw: list[str] = response["data"]
        dates = []
        for date_raw in dates_raw:
            try:
                dt = dateutil.parser.parse(date_raw)
            except Exception as e:
                logger.exception(e)
                continue

            dates.append(dt)
        return dates

    except (
        json.JSONDecodeError,
        asyncio.TimeoutError,
        requests.exceptions.ReadTimeout,
        requests.exceptions.SSLError,
        urllib3.exceptions.ProxyError,
        requests.exceptions.ProxyError,
        aiohttp.ClientProxyConnectionError,
        aiohttp.client_exceptions.ContentTypeError,
        aiohttp.client_exceptions.ClientConnectionError,
        aiohttp.client_exceptions.ClientHttpProxyError,
        aiohttp.client_exceptions.ClientResponseError,
    ) as e:
        return []
    except Exception as e:
        msg = f"{e}:\n{traceback.format_exc()}"
        logger.error(msg)
        return []


async def start_registration(month: int, tip_formular: int, use_proxy: bool):
    if use_proxy:
        proxies = (
            await GeoNode().list_proxy() + await FreeProxies().list_proxy()
        )
        filtered = await filter_proxies(proxies, debug=True)

    async def get_ip(session: aiohttp.ClientSession, proxy: str = None):
        try:
            async with session.get(
                "https://api.ipify.org", proxy=proxy
            ) as resp:
                return await resp.text()
        except Exception:
            return None

    while True:
        if use_proxy:
            pprint(filtered.proxies)
            if not filtered.proxies:
                await asyncio.sleep(2)
                continue

            session, proxies = await filtered.get_session()
        else:
            session = AiohttpSession().generate(close_connector=True)
            proxies = [None]

        async with session:
            tasks = [
                get_free_dates(session, month, tip_formular, proxy=proxy)
                for proxy in proxies
            ]
            tasks = [get_ip(session, proxy=proxy) for proxy in proxies]
            chunks = divide_list(tasks)
            for chunk in chunks:
                results = await asyncio.gather(*chunk)
                dates = [result for result in results if result]
                if dates:
                    pprint(len(dates))
                    print("\n")
                await asyncio.sleep(1.5)
                ...


async def main():
    tip_formular = 3
    month = 11
    proxy = True

    await start_registration(month, tip_formular, proxy)
    users_data = get_users_data_from_xslx()
    pprint(users_data)


if __name__ == "__main__":
    asyncio.run(main())
