import asyncio
from datetime import date, datetime
import json
from os import device_encoding
from pprint import pprint

import random
import string
from tkinter import N
import traceback
import aiofiles
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
from registrator_romania.bot import send_msg_into_chat
from registrator_romania.proxy import (
    FreeProxies,
    FreeProxiesList,
    GeoNode,
    divide_list,
    filter_proxies,
)

from registrator_romania.new_request_registrator import (
    URL_GENERAL,
    get_captcha_response,
    get_error,
    get_users_data_from_xslx,
    is_success,
)
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


async def make_registration(
    session: aiohttp.ClientSession,
    user_data: dict,
    tip_formular: int,
    reg_dt: date,
    proxy: str = None,
):
    ua = ua_generator.generate()
    headers = {
        "Accept": "*/*",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
        "Cache-Control": "max-age=0",
        "Connection": "keep-alive",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://programarecetatenie.eu",
        "Referer": "https://programarecetatenie.eu/programare_online",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }

    for key, value in ua.headers.get().items():
        headers[key] = value

    data = {
        "tip_formular": str(tip_formular),
        "nume_pasaport": user_data["Nume Pasaport"].strip(),
        "data_nasterii": user_data["Data nasterii"].strip(),
        "prenume_pasaport": user_data["Prenume Pasaport"].strip(),
        "locul_nasterii": user_data["Locul naşterii"].strip(),
        "prenume_mama": user_data["Prenume Mama"].strip(),
        "prenume_tata": user_data["Prenume Tata"].strip(),
        "email": user_data["Adresa de email"].strip(),
        "numar_pasaport": user_data["Serie și număr Pașaport"].strip(),
        "data_programarii": reg_dt.strftime("%Y-%m-%d"),
        "gdpr": "1",
        "honeypot": "",
        "g-recaptcha-response": await get_captcha_response(),
    }

    try:
        async with session.post(URL_GENERAL, data=data, proxy=proxy) as resp:
            return (await resp.text(), user_data)
    except (aiohttp.ClientHttpProxyError, aiohttp.ClientProxyConnectionError):
        async with session.post(URL_GENERAL, data=data) as resp:
            return (await resp.text(), user_data)


async def start_registration(
    month: int,
    tip_formular: int,
    use_proxy: bool,
    users_data: list[dict[str, str]],
):
    if use_proxy:
        proxies = (
            await GeoNode().list_proxy()
            + await FreeProxies().list_proxy()
            + await FreeProxiesList().list_proxy()
        )
        filtered = await filter_proxies(proxies, debug=False)

    while True:
        start = datetime.now()
        if use_proxy:
            print(f"We have {len(filtered.proxies)} proxies")
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
            chunks = divide_list(tasks)
            for chunk in chunks:
                results = await asyncio.gather(*chunk)
                stop = datetime.now()
                print(stop - start)
                # pprint(results)
                continue
                successfully_results = [result for result in results if result]
                dates = [date for dates in dates_chunks for date in dates]
                dates = [
                    date
                    for date in dates
                    if date.month == month and date.year == datetime.now().year
                ]

                if dates:
                    pprint(len(dates))
                    print("\n")
                    ...

                elif use_proxy and not dates:
                    dates = await get_free_dates(
                        session, month, tip_formular, proxy=None
                    )

                # if dates:
                #     for date in dates:
                #         for user_data in users_data:
                #             result = await make_registration(
                #                 session,
                #                 user_data,
                #                 tip_formular,
                #                 date,
                #             )

                #             if not isinstance(result, tuple):
                #                 continue

                #             html, _ = result

                #             if not isinstance(html, str) or not html:
                #                 continue

                #             name = user_data["Nume Pasaport"]
                #             fn = f"user_{name}.html"
                #             async with aiofiles.open(
                #                 fn, "w", encoding="utf-8"
                #             ) as f:
                #                 await f.write(html)

                #             if is_success(html) is False:
                #                 text_error = get_error(html)
                #                 logger.error(
                #                     f"Registration for {name} was failed. Error:\n"
                #                     f"{text_error}.\nDate of registration: {date}\n"
                #                     f"Tip formular: {tip_formular}"
                #                 )

                #             else:
                #                 us_data = json.dumps(
                #                     user_data, ensure_ascii=False, indent=2
                #                 )
                #                 msg = (
                #                     f"Registration for {name} was successfully.\n"
                #                     f"{us_data}\n"
                #                 )
                #                 logger.success(msg)
                #                 tasks.append(
                #                     asyncio.get_running_loop().create_task(
                #                         send_msg_into_chat(msg, file=fn)
                #                     )
                #                 )
                #                 users_data.remove(user_data)

                await asyncio.sleep(1.5)
                ...


async def main():
    tip_formular = 5
    month = 11
    proxy = True

    users_data = get_users_data_from_xslx()
    # pprint(users_data)
    await start_registration(month, tip_formular, proxy, users_data)


if __name__ == "__main__":
    asyncio.run(main())
