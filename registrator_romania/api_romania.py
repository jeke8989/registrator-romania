import asyncio
import calendar
from datetime import datetime, date, timedelta
from operator import le
from pprint import pprint
import random
import re
import time
from typing import Required, TypedDict
from zoneinfo import ZoneInfo
import aiofiles
from flask import session
from loguru import logger

import aiohttp
import bs4
from pyjsparser import parse
import ua_generator
from pypasser import reCaptchaV3
from registrator_romania import bot
from registrator_romania.new_request_registrator import (
    generate_fake_users_data,
    get_users_data_from_xslx,
)
from registrator_romania.parser import get_users_data_from_docx
from registrator_romania.proxy import (
    AIOHTTP_NET_ERRORS,
    AiohttpSession,
    FreeProxies,
    FreeProxiesList,
    GeoNode,
    ImRavzanProxyList,
    LionKingsProxy,
    ProxyMaster,
    AutomaticProxyPool,
    TheSpeedX,
)


UserData = TypedDict(
    "UserData",
    {
        "Nume Pasaport": Required[str],
        "Prenume Pasaport": Required[str],
        "Data nasterii": Required[str],
        "Locul naşterii": Required[str],
        "Prenume Mama": Required[str],
        "Prenume Tata": Required[str],
        "Adresa de email": Required[str],
        "Serie și număr Pașaport": Required[str],
    },
)


async def get_proxy_pool(start: bool = True, debug: bool = False):
    proxies_classes = (
        GeoNode(),
        FreeProxies(),
        FreeProxiesList(),
        ImRavzanProxyList(),
        LionKingsProxy(),
        TheSpeedX(),
        ProxyMaster(),
    )
    proxies = [
        proxy
        for proxy_class in proxies_classes
        for proxy in await proxy_class.list_http_proxy()
    ]

    if debug:
        logger.debug(f"Total raw proxies - {len(proxies)}")

    pool = AutomaticProxyPool(proxies=proxies, debug=debug, second_check=True)
    if start:
        await pool
    return pool


class APIRomania:
    BASE_URL = "https://programarecetatenie.eu"
    SITE_TOKEN = "6LcnPeckAAAAABfTS9aArfjlSyv7h45waYSB_LwT"
    MAIN_URL = f"{BASE_URL}/programare_online"
    STATUS_DAYS_URL = f"{BASE_URL}/status_zile"
    STATUS_PLACES_URL = f"{BASE_URL}/status_zii"
    REGISTRATIONS_LIST_URL = f"{BASE_URL}/verificare_programare?ajax=true"
    CAPTCHA_BASE_URL = "https://www.google.com/recaptcha"
    CAPTCHA_URL = (
        f"{CAPTCHA_BASE_URL}/api2/anchor?ar=1"
        f"&k={SITE_TOKEN}&co=aHR0cHM6Ly9wcm9ncmFtYXJlY2V0YX"
        "RlbmllLmV1OjQ0Mw..&hl=ru&v=DH3nyJMamEclyfe-nztbfV8S"
        "&size=invisible&cb=ulevyud5loaq"
    )

    def __init__(self, debug: bool = False, semaphore_value: int = 15) -> None:
        self._sessionmaker = AiohttpSession()
        self._connections_pool = self._sessionmaker.generate_connector()
        self._proxy_pool: AutomaticProxyPool = None
        self._debug = debug
        self._main_html = None
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(semaphore_value)

    async def get_proxy_pool(self):
        if not self._proxy_pool:
            self._proxy_pool = await get_proxy_pool(
                start=True, debug=self._debug
            )

        return self._proxy_pool

    async def get_recaptcha_token(
        self, proxy: str = None, use_proxy: bool = False
    ):
        """Async get and return data for `g-recaptcha-response` field."""
        base_url = self.CAPTCHA_BASE_URL
        post_data = "v={}&reason=q&c={}&k={}&co={}&hl=en&size=invisible&chr=%5B89%2C64%2C27%5D&vh=13599012192&bg=!q62grYxHRvVxjUIjSFNd0mlvrZ-iCgIHAAAB6FcAAAANnAkBySdqTJGFRK7SirleWAwPVhv9-XwP8ugGSTJJgQ46-0IMBKN8HUnfPqm4sCefwxOOEURND35prc9DJYG0pbmg_jD18qC0c-lQzuPsOtUhHTtfv3--SVCcRvJWZ0V3cia65HGfUys0e1K-IZoArlxM9qZfUMXJKAFuWqZiBn-Qi8VnDqI2rRnAQcIB8Wra6xWzmFbRR2NZqF7lDPKZ0_SZBEc99_49j07ISW4X65sMHL139EARIOipdsj5js5JyM19a2TCZJtAu4XL1h0ZLfomM8KDHkcl_b0L-jW9cvAe2K2uQXKRPzruAvtjdhMdODzVWU5VawKhpmi2NCKAiCRUlJW5lToYkR_X-07AqFLY6qi4ZbJ_sSrD7fCNNYFKmLfAaxPwPmp5Dgei7KKvEQmeUEZwTQAS1p2gaBmt6SCOgId3QBfF_robIkJMcXFzj7R0G-s8rwGUSc8EQzT_DCe9SZsJyobu3Ps0-YK-W3MPWk6a69o618zPSIIQtSCor9w_oUYTLiptaBAEY03NWINhc1mmiYu2Yz5apkW_KbAp3HD3G0bhzcCIYZOGZxyJ44HdGsCJ-7ZFTcEAUST-aLbS-YN1AyuC7ClFO86CMICVDg6aIDyCJyIcaJXiN-bN5xQD_NixaXatJy9Mx1XEnU4Q7E_KISDJfKUhDktK5LMqBJa-x1EIOcY99E-eyry7crf3-Hax3Uj-e-euzRwLxn2VB1Uki8nqJQVYUgcjlVXQhj1X7tx4jzUb0yB1TPU9uMBtZLRvMCRKvFdnn77HgYs5bwOo2mRECiFButgigKXaaJup6NM4KRUevhaDtnD6aJ8ZWQZTXz_OJ74a_OvPK9eD1_5pTG2tUyYNSyz-alhvHdMt5_MAdI3op4ZmcvBQBV9VC2JLjphDuTW8eW_nuK9hN17zin6vjEL8YIm_MekB_dIUK3T1Nbyqmyzigy-Lg8tRL6jSinzdwOTc9hS5SCsPjMeiblc65aJC8AKmA5i80f-6Eg4BT305UeXKI3QwhI3ZJyyQAJTata41FoOXl3EF9Pyy8diYFK2G-CS8lxEpV7jcRYduz4tEPeCpBxU4O_KtM2iv4STkwO4Z_-c-fMLlYu9H7jiFnk6Yh8XlPE__3q0FHIBFf15zVSZ3qroshYiHBMxM5BVQBOExbjoEdYKx4-m9c23K3suA2sCkxHytptG-6yhHJR3EyWwSRTY7OpX_yvhbFri0vgchw7U6ujyoXeCXS9N4oOoGYpS5OyFyRPLxJH7yjXOG2Play5HJ91LL6J6qg1iY8MIq9XQtiVZHadVpZVlz3iKcX4vXcQ3rv_qQwhntObGXPAGJWEel5OiJ1App7mWy961q3mPg9aDEp9VLKU5yDDw1xf6tOFMwg2Q-PNDaKXAyP_FOkxOjnu8dPhuKGut6cJr449BKDwbnA9BOomcVSztEzHGU6HPXXyNdZbfA6D12f5lWxX2B_pobw3a1gFLnO6mWaNRuK1zfzZcfGTYMATf6d7sj9RcKNS230XPHWGaMlLmNxsgXkEN7a9PwsSVwcKdHg_HU4vYdRX6vkEauOIwVPs4dS7yZXmtvbDaX1zOU4ZYWg0T42sT3nIIl9M2EeFS5Rqms_YzNp8J-YtRz1h5RhtTTNcA5jX4N-xDEVx-vD36bZVzfoMSL2k85PKv7pQGLH-0a3DsR0pePCTBWNORK0g_RZCU_H898-nT1syGzNKWGoPCstWPRvpL9cnHRPM1ZKemRn0nPVm9Bgo0ksuUijgXc5yyrf5K49UU2J5JgFYpSp7aMGOUb1ibrj2sr-D63d61DtzFJ2mwrLm_KHBiN_ECpVhDsRvHe5iOx_APHtImevOUxghtkj-8RJruPgkTVaML2MEDOdL_UYaldeo-5ckZo3VHss7IpLArGOMTEd0bSH8tA8CL8RLQQeSokOMZ79Haxj8yE0EAVZ-k9-O72mmu5I0wH5IPgapNvExeX6O1l3mC4MqLhKPdOZOnTiEBlSrV4ZDH_9fhLUahe5ocZXvXqrud9QGNeTpZsSPeIYubeOC0sOsuqk10sWB7NP-lhifWeDob-IK1JWcgFTytVc99RkZTjUcdG9t8prPlKAagZIsDr1TiX3dy8sXKZ7d9EXQF5P_rHJ8xvmUtCWqbc3V5jL-qe8ANypwHsuva75Q6dtqoBR8vCE5xWgfwB0GzR3Xi_l7KDTsYAQIrDZVyY1UxdzWBwJCrvDrtrNsnt0S7BhBJ4ATCrW5VFPqXyXRiLxHCIv9zgo-NdBZQ4hEXXxMtbem3KgYUB1Rals1bbi8X8MsmselnHfY5LdOseyXWIR2QcrANSAypQUAhwVpsModw7HMdXgV9Uc-HwCMWafOChhBr88tOowqVHttPtwYorYrzriXNRt9LkigESMy1bEDx79CJguitwjQ9IyIEu8quEQb_-7AEXrfDzl_FKgASnnZLrAfZMtgyyddIhBpgAvgR_c8a8Nuro-RGV0aNuunVg8NjL8binz9kgmZvOS38QaP5anf2vgzJ9wC0ZKDg2Ad77dPjBCiCRtVe_dqm7FDA_cS97DkAwVfFawgce1wfWqsrjZvu4k6x3PAUH1UNzQUxVgOGUbqJsaFs3GZIMiI8O6-tZktz8i8oqpr0RjkfUhw_I2szHF3LM20_bFwhtINwg0rZxRTrg4il-_q7jDnVOTqQ7fdgHgiJHZw_OOB7JWoRW6ZlJmx3La8oV93fl1wMGNrpojSR0b6pc8SThsKCUgoY6zajWWa3CesX1ZLUtE7Pfk9eDey3stIWf2acKolZ9fU-gspeACUCN20EhGT-HvBtNBGr_xWk1zVJBgNG29olXCpF26eXNKNCCovsILNDgH06vulDUG_vR5RrGe5LsXksIoTMYsCUitLz4HEehUOd9mWCmLCl00eGRCkwr9EB557lyr7mBK2KPgJkXhNmmPSbDy6hPaQ057zfAd5s_43UBCMtI-aAs5NN4TXHd6IlLwynwc1zsYOQ6z_HARlcMpCV9ac-8eOKsaepgjOAX4YHfg3NekrxA2ynrvwk9U-gCtpxMJ4f1cVx3jExNlIX5LxE46FYIhQ"

        session = await self.get_session(with_proxy_if_exists=use_proxy)
        session._default_headers = self.headers_captcha_url

        regex = r"(?P<endpoint>[api2|enterprise]+)\/anchor\?(?P<params>.*)"
        data = re.finditer(regex, self.CAPTCHA_URL)
        assert data
        data = next(data).groupdict()

        url_get = f"{base_url}/{data["endpoint"]}/anchor?{data["params"]}"
        async with session:
            try:
                async with session.get(url_get, proxy=proxy) as resp:
                    response = await resp.text()

                results = re.findall(
                    r'"recaptcha-token" value="(.*?)"', response
                )
                token = None if not results else results[0]
                if not token:
                    return

                params = dict(
                    pair.split("=") for pair in data["params"].split("&")
                )
                this_post_data = post_data.format(
                    params["v"], token, params["k"], params["co"]
                )

                url_post = (
                    f"{base_url}/{data["endpoint"]}/reload?k={params["k"]}"
                )
                async with session.post(
                    url_post, data=this_post_data, proxy=proxy
                ) as resp:
                    response = await resp.text()

                results = re.findall(r'"rresp","(.*?)"', response)
                if not results:
                    return

                return results[0]
            except AIOHTTP_NET_ERRORS as e:
                pass

    async def get_captcha_token(self):
        """Async get and return data for `g-recaptcha-response` field."""
        return await asyncio.to_thread(reCaptchaV3, self.CAPTCHA_URL)

    def get_error_registration_as_text(self, html_code: str) -> str:
        r"""
        Return text of error in <p class="alert alert-danger"> tag
        """
        s = bs4.BeautifulSoup(html_code, "lxml")
        alert_tag = s.find("p", class_="alert alert-danger")
        if not alert_tag:
            return ""
        return alert_tag.text

    def is_success_registration(self, html_code: str) -> bool:
        r"""
        Return True if html response have paragraph `Felicitări`
        otherwise False.
        """
        if "<p>Felicitări!</p>" in html_code:
            return True
        return False

    @property
    def headers_main_url(self) -> dict[str, str]:
        headers = {
            "Accept": "*/*",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
            "Referer": "https://programarecetatenie.eu/programare_online",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }
        for k, v in ua_generator.generate().headers.get().items():
            headers[k] = v
        return headers

    @property
    def headers_captcha_url(self) -> dict[str, str]:
        return {"Content-Type": "application/x-www-form-urlencoded"}

    @property
    def headers_registrations_list_url(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
            "Connection": "keep-alive",
            "Origin": "https://programarecetatenie.eu",
            "Referer": "https://programarecetatenie.eu/verificare_programare",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "X-Requested-With": "XMLHttpRequest",
        }
        for k, v in ua_generator.generate().headers.get().items():
            headers[k] = v
        return headers

    @property
    def headers_dates_url(self) -> dict[str, str]:
        headers = {
            "Accept": "*/*",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
            "Connection": "keep-alive",
            "Origin": "https://programarecetatenie.eu",
            "Referer": "https://programarecetatenie.eu/programare_online",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "X-Requested-With": "XMLHttpRequest",
        }
        for k, v in ua_generator.generate().headers.get().items():
            headers[k] = v
        return headers

    @property
    def headers_places_url(self) -> dict[str, str]:
        headers = {
            "Accept": "*/*",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
            "Connection": "keep-alive",
            "Origin": "https://programarecetatenie.eu",
            "Referer": "https://programarecetatenie.eu/programare_online",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "X-Requested-With": "XMLHttpRequest",
        }
        for k, v in ua_generator.generate().headers.get().items():
            headers[k] = v
        return headers

    @property
    def headers_registration_url(self) -> dict[str, str]:
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
            "Origin": "https://programarecetatenie.eu",
            "Referer": "https://programarecetatenie.eu/programare_online",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }
        for k, v in ua_generator.generate().headers.get().items():
            headers[k] = v
        return headers

    async def _get_main_html(self):
        if self._main_html:
            return self._main_html

        # session = self._sessionmaker.generate(connector=self._connections_pool)
        session = await self.get_session()
        session._default_headers = self.headers_main_url

        async with session:
            proxies = [None]
            while True:
                try:
                    for proxy in proxies:
                        async with session.get(
                            self.MAIN_URL, proxy=proxy
                        ) as resp:
                            reason = resp.reason.lower()

                            if reason.count("forbidden") and proxies == [None]:
                                pool = await self.get_proxy_pool()
                                url = self.MAIN_URL
                                headers = self.headers_main_url
                                proxies = await pool.collect_valid_proxies(
                                    url=url, headers=headers
                                )
                                continue

                            return await resp.text()

                except AIOHTTP_NET_ERRORS:
                    await asyncio.sleep(1.5)
                    continue

    async def get_session(
        self, with_proxy_if_exists: bool = True, timeout: int = 5
    ) -> aiohttp.ClientSession:
        if self._proxy_pool and with_proxy_if_exists:
            return await self._proxy_pool.get_session(timeout=timeout)
        return self._sessionmaker.generate(
            self._connections_pool, total_timeout=timeout
        )

    async def _get_default_disabled_weekdays(
        self, year: int, month: int, tip_formular: int
    ) -> list[int]:
        html = await self._get_main_html()
        soup = bs4.BeautifulSoup(html, "lxml")
        tag_script = soup.find_all("script")[-2]
        js_script = tag_script.text

        parsed = parse(js_script)

        obj = {}
        func_body = parsed["body"][0]["expression"]["arguments"][0]["body"]
        cases = func_body["body"][14]["consequent"]["body"][3]["expression"][
            "arguments"
        ][0]["properties"][6]["value"]["body"]["body"][0]["cases"]

        for case in cases:
            k = case["test"]["value"]
            v = [
                int(element["value"])
                for element in case["consequent"][0]["declarations"][0]["init"][
                    "elements"
                ]
            ]
            obj[str(k)] = v

        return obj[str(tip_formular)]

    async def _get_disabled_days(
        self, year: int, month: int, tip_formular: int
    ):
        # session = self._sessionmaker.generate(connector=self._connections_pool)
        session = await self.get_session()
        session._default_headers = self.headers_dates_url

        month = f"0{month}" if len(str(month)) == 1 else str(month)
        form_data = aiohttp.FormData()
        form_data.add_field("azi", f"{year}-{month}")
        form_data.add_field("tip_formular", str(tip_formular))
        async with session:
            try:
                async with session.post(
                    self.STATUS_DAYS_URL, data=form_data
                ) as resp:
                    raw = await resp.read()
                    response = await resp.json(content_type=resp.content_type)
            except Exception:
                return

        return [
            date.day
            for date_string in response["data"]
            for date in [datetime.strptime(date_string, "%Y-%m-%d")]
            if date.month == int(month) and date.year == int(year)
        ]

    async def get_free_days(
        self, month: int, tip_formular: int, year: int = None
    ):
        if not year:
            year = datetime.now().year

        weekdays_disable = await self._get_default_disabled_weekdays(
            year=year, month=month, tip_formular=tip_formular
        )
        days_disable = await self._get_disabled_days(
            year=year, month=month, tip_formular=tip_formular
        )
        if not days_disable or not weekdays_disable:
            return []

        dates = []
        for day in range(1, int(calendar.monthrange(year, month)[1]) + 1):
            dt = date(year, month, day)
            weekday_num = 0 if dt.isoweekday() == 7 else dt.isoweekday()
            if weekday_num not in weekdays_disable and day not in days_disable:
                dates.append(dt.strftime("%Y-%m-%d"))
        return dates

    async def get_free_places_for_date(
        self, tip_formular: int, month: int, day: int, year: int = None
    ):
        if not year:
            year = datetime.now().year
        month = f"0{month}" if len(str(month)) == 1 else str(month)

        # session = self._sessionmaker.generate(self._connections_pool)
        session = await self.get_session()
        session._default_headers = self.headers_places_url

        form_data = aiohttp.FormData()
        form_data.add_field("azi", f"{year}-{month}-{day}")
        form_data.add_field("tip_formular", tip_formular)

        async with session:
            try:
                async with session.post(
                    self.STATUS_PLACES_URL, data=form_data
                ) as resp:
                    raw = await resp.read()
                    response = await resp.json(content_type=resp.content_type)
            except AIOHTTP_NET_ERRORS:
                return

        return response["numar_ramase"]

    async def make_registration(
        self,
        user_data: UserData,
        registration_date: datetime,
        tip_formular: int,
        proxy: str = None,
        queue: asyncio.Queue = None,
    ):
        g_recaptcha_response = await self.get_recaptcha_token()
        if not g_recaptcha_response:
            return
        data = {
            "tip_formular": tip_formular,
            "nume_pasaport": user_data["Nume Pasaport"].strip(),
            "data_nasterii": user_data["Data nasterii"].strip(),
            "prenume_pasaport": user_data["Prenume Pasaport"].strip(),
            "locul_nasterii": user_data["Locul naşterii"].strip(),
            "prenume_mama": user_data["Prenume Mama"].strip(),
            "prenume_tata": user_data["Prenume Tata"].strip(),
            "email": user_data["Adresa de email"].strip(),
            "numar_pasaport": user_data["Serie și număr Pașaport"].strip(),
            "data_programarii": registration_date.strftime("%Y-%m-%d"),
            "gdpr": "1",
            "honeypot": "",
            "g-recaptcha-response": g_recaptcha_response,
        }

        use_proxy = True
        session = await self.get_session(with_proxy_if_exists=use_proxy)
        session._default_headers = self.headers_registration_url
        start = datetime.now()
        async with session:
            raw = None
            try:
                async with asyncio.timeout(5):
                    async with session.post(
                        self.MAIN_URL, data=data, proxy=proxy
                    ) as resp:
                        raw = await resp.read()
                        html = await resp.text()
                error_text = None
                username = user_data["Nume Pasaport"]

                if self.is_success_registration(html):
                    logger.info(
                        f"{username} registered successfully by proxy {proxy}"
                    )
                    if queue:
                        await queue.put((user_data, html))
                else:
                    error_text = self.get_error_registration_as_text(html)
                    logger.info(
                        f"{username} got an error from server: {error_text}"
                    )

                return html
            except asyncio.TimeoutError as e:
                raise e
            except AIOHTTP_NET_ERRORS as e:
                raw_msg = (
                    "Not found" if not raw else raw.decode(errors="replace")
                )
                logger.warning(
                    f"{self.MAIN_URL}\n"
                    f"{e.__class__.__name__}: {e}. Raw response: {raw_msg}.\n "
                    f"{datetime.now() - start}\nLast proxy - "
                    f"{self._proxy_pool.last_proxy_used}\n\n"
                )
                pass

    async def see_registrations(
        self,
        tip_formular: str = "",
        email: str = "",
        nume: str = "",
        prenume: str = "",
        data_nasterii: str = "",
        numar_pasaport: str = "",
        limit: int = 500,
        data_programarii: list[datetime] = None,
    ):
        if data_programarii:
            dt_start, dt_end = map(
                lambda dt: dt.strftime("%Y-%m-%d"), data_programarii
            )
        else:
            dt_start, dt_end = ("", "")
        data = {
            "draw": "4",
            "columns[0][data]": "tip_formular",
            "columns[0][name]": "",
            "columns[0][searchable]": "true",
            "columns[0][orderable]": "false",
            "columns[0][search][value]": tip_formular,
            "columns[0][search][regex]": "false",
            "columns[1][data]": "email",
            "columns[1][name]": "",
            "columns[1][searchable]": "true",
            "columns[1][orderable]": "false",
            "columns[1][search][value]": email,
            "columns[1][search][regex]": "false",
            "columns[2][data]": "nume_pasaport",
            "columns[2][name]": "",
            "columns[2][searchable]": "true",
            "columns[2][orderable]": "false",
            "columns[2][search][value]": nume,
            "columns[2][search][regex]": "false",
            "columns[3][data]": "prenume_pasaport",
            "columns[3][name]": "",
            "columns[3][searchable]": "true",
            "columns[3][orderable]": "false",
            "columns[3][search][value]": prenume,
            "columns[3][search][regex]": "false",
            "columns[4][data]": "data_nasterii",
            "columns[4][name]": "",
            "columns[4][searchable]": "true",
            "columns[4][orderable]": "false",
            "columns[4][search][value]": data_nasterii,
            "columns[4][search][regex]": "false",
            "columns[5][data]": "data_programarii",
            "columns[5][name]": "",
            "columns[5][searchable]": "true",
            "columns[5][orderable]": "false",
            "columns[5][search][value]": f"{dt_start} AND {dt_end}",
            "columns[5][search][regex]": "false",
            "columns[6][data]": "ora_programarii",
            "columns[6][name]": "",
            "columns[6][searchable]": "true",
            "columns[6][orderable]": "false",
            "columns[6][search][value]": "",
            "columns[6][search][regex]": "false",
            "columns[7][data]": "numar_pasaport",
            "columns[7][name]": "",
            "columns[7][searchable]": "true",
            "columns[7][orderable]": "false",
            "columns[7][search][value]": numar_pasaport,
            "columns[7][search][regex]": "false",
            "start": "0",
            "length": limit,
            "search[value]": "",
            "search[regex]": "false",
        }

        session = self._sessionmaker.generate(
            self._connections_pool, close_connector=True
        )
        session._default_headers = self.headers_registrations_list_url
        async with session:
            try:
                async with session.post(
                    self.REGISTRATIONS_LIST_URL, data=data
                ) as resp:
                    raw = await resp.read()
                    return await resp.json(content_type=resp.content_type)
            except Exception:
                pass


async def get_unregister_users(
    users_data_list: list[UserData],
    registration_dates: list[datetime] = None,
    tip_formular: int = "",
    **filter_kwargs,
):
    api = APIRomania()
    response = await api.see_registrations(
        tip_formular=tip_formular,
        data_programarii=registration_dates,
        **filter_kwargs,
    )
    registered_users = response["data"]
    registered_usernames = [
        (obj["nume_pasaport"].lower(), obj["prenume_pasaport"].lower())
        for obj in registered_users
    ]

    unregistered_users = []
    for user in users_data_list:
        names = (
            user["Nume Pasaport"].lower(),
            user["Prenume Pasaport"].lower(),
        )
        if names not in registered_usernames:
            unregistered_users.append(user)

    return unregistered_users


async def registration(tip_formular: int, registration_date: datetime):
    api = APIRomania()
    users_data = get_users_data_from_docx() + get_users_data_from_xslx()
    filtered_us_data = await get_unregister_users(
        users_data,
        registration_dates=[
            (registration_date - timedelta(days=5)),
            registration_date,
        ],
        tip_formular=tip_formular,
    )
    print(
        f"Total users - {len(users_data)}, not registered - {len(filtered_us_data)} yet"
    )
    users_data = filtered_us_data
    return
    # users_data = generate_fake_users_data(79)
    assert all(
        k in [key for obj in users_data for key in list(obj.keys())]
        for obj in generate_fake_users_data(1)
        for k in list(obj.keys())
    )

    pool = await api.get_proxy_pool()
    report_tasks = []
    successfully_registered = []
    queue = asyncio.Queue()

    while len(pool.proxies) < 5:
        print(f"Wait for 5 proxies, now we have {len(pool.proxies)} proxies")
        await asyncio.sleep(1)

    proxies = []

    async def update_proxy_list():
        nonlocal proxies
        try:
            while True:
                unstorted_proxies = await pool.collect_valid_proxies(
                    api.MAIN_URL, headers=api.headers_main_url
                )
                sorted_proxies = pool.sort_proxies_by_timeout(unstorted_proxies)

                proxies = [obj["proxy"] for obj in sorted_proxies]
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass

    do_check_places = False
    task = asyncio.create_task(update_proxy_list())
    while not proxies:
        await asyncio.sleep(1)

    start = None
    while True:
        dt = moscow_dt_now()
        if len(proxies) < 2:
            print(
                f"Wait for 2 proxies for site, "
                f"now we have {len(proxies)} for site"
            )
            await asyncio.sleep(1)
            continue

        if not start:
            start = datetime.now()

        print(
            f"We have {len(pool.proxies)} proxy in pool. "
            f"And {len(proxies)} for site"
        )

        if do_check_places:
            places = await api.get_free_places_for_date(
                tip_formular=tip_formular,
                month=registration_date.month,
                day=registration_date.day,
                year=registration_date.year,
            )
            print(f"Free places - {places}")
            if not places and successfully_registered:
                break
            elif not places:
                continue
            else:
                do_check_places = False

        users_for_registrate = [
            u for u in users_data if u not in successfully_registered
        ]
        tasks = [
            api.make_registration(
                user_data,
                registration_date=registration_date,
                tip_formular=tip_formular,
                queue=queue,
                proxy=random.choice(proxies),
            )
            for user_data in users_for_registrate
        ]

        start = datetime.now()
        try:
            results = await asyncio.gather(*tasks)
        except asyncio.TimeoutError:
            print("timeout")
        else:
            empty = [r for r in results if not r]
            print(
                f"Sended {len(tasks)} requests ({len(empty)} failed) "
                f"in {datetime.now() - start}."
            )

        while not queue.empty():
            user_data, html = queue.get_nowait()
            username = user_data["Nume Pasaport"]

            fn = f"async_test/{username}_{time.time()}_success_with-proxy.html"
            # with open(fn, "w") as f:
            #     f.write(html)

            report_tasks.append(
                bot.send_msg_into_chat(
                    f"Успешная попытка регистрарции для {username}", fn
                )
            )
            successfully_registered.append(user_data)

        if len(successfully_registered) >= len(users_data):
            break

        if dt.hour == 9 and dt.minute >= 1:
            break

    print(f"script took {datetime.now() - start}")
    task.cancel()
    for task in report_tasks:
        continue
        await task
        await asyncio.sleep(3)


def moscow_dt_now():
    return datetime.now().astimezone(tz=ZoneInfo("Europe/Moscow"))


async def main():
    tip_formular = 4
    # tip_formular = 2
    moscow_dt = moscow_dt_now()
    registration_date = datetime(
        # year=moscow_dt.year,
        # month=11,
        # day=datetime.now().day,
        year=moscow_dt.year,
        month=11,
        day=14,
    )
    start = datetime.now()
    await registration(tip_formular, registration_date)
    print(datetime.now() - start, "script finish")
    ...


if __name__ == "__main__":
    asyncio.run(main())
