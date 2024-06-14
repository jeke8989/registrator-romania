from __future__ import annotations

import asyncio
import json
import random
from calendar import calendar, monthrange
from datetime import date, datetime, timedelta
import re
from typing import Literal, Optional, Self

import aiofiles
import aiohttp
import pyjsparser
import requests
import ua_generator
from bs4 import BeautifulSoup, Tag
from loguru import logger
from pypasser import reCaptchaV3
from zoneinfo import ZoneInfo

from registrator_romania.google_spread import get_df
from registrator_romania.proxy import aiohttp_session


class RequestsRegistrator:
    """Registrator by request.

    Parameters
    ----------
    tip_formular : int
        code for articolur.
    registration_date : Optional[date], optional
        pass date for appointment. if None *to_get_registration_date,
        by default None
    mode_to_get_registration_date : Literal["nearest", "freest", "random"],
        optional

        If nearest it select nearest date in passed month and year
        If random it select random date
        If freest it select freest date, by default None
    month_to_get_registration_date : Optional[int], optional
        month of registration date, by default None
    year_to_get_registration_date : Optional[int], optional
        year of registration date, by default None
    """

    def __init__(
        self,
        tip_formular: int,
        registration_date: Optional[date] = None,
        mode_to_get_registration_date: Optional[
            Literal["nearest", "freest", "random"]
        ] = None,
        month_to_get_registration_date: Optional[int] = None,
        year_to_get_registration_date: Optional[int] = None,
    ) -> None:
        self._registration_date = registration_date

        self._captcha_url = (
            "https://www.google.com/recaptcha/api2/anchor?ar=1"
            f"&k={SITE_TOKEN}&co=aHR0cHM6Ly9wcm9ncmFtYXJlY2V0YX"
            "RlbmllLmV1OjQ0Mw..&hl=ru&v=DH3nyJMamEclyfe-nztbfV8S"
            "&size=invisible&cb=ulevyud5loaq"
        )
        self._tip_formular = tip_formular

        self._programare_html: str = None
        self._freest_date: datetime = None
        self._disabled_dates_in_month: list[datetime] = None

        self._mode_to_get_registration_date = mode_to_get_registration_date
        self._month_to_get_registration_date = month_to_get_registration_date
        self._year_to_get_registration_date = year_to_get_registration_date

    @property
    def headers(self):
        """Return random headers."""
        ua = ua_generator.generate()
        headers = {
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9"
                ",image/avif,image/webp,image/apng,*/*;q=0.8,application"
                "/signed-exchange;v=b3;q=0.7"
            ),
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://programarecetatenie.eu",
            "Referer": "https://programarecetatenie.eu/programare_online",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Upgrade-Insecure-Requests": "1",
        }
        for key, value in ua.headers.get().items():
            headers[key] = value

        return headers

    async def get_captcha_response(self) -> str:
        """Async get and return `g-recaptcha-response` field."""
        return await asyncio.to_thread(reCaptchaV3, self._captcha_url)

    def find_days_disable(
        self, js_code: str, tip_formular_value: int
    ) -> list[int, None]:
        r"""Get disabled weekdays in articolur by `tip_formular_value`.

        Search in js script and return list with disabled weekdays
        by `tip_formular_value`

        Parameters
        ----------
        js_code : str
            javascript code
        tip_formular_value : int
            tip formular

        Returns
        -------
        list[int, None]
            empty list if not find, otherwise list with disabled day(s).
        """
        parser = pyjsparser.PyJsParser()
        parsed_code = parser.parse(js_code)

        for stmt in parsed_code["body"]:
            if (
                stmt["type"] != "ExpressionStatement"
                or stmt["expression"]["type"] != "CallExpression"
            ):
                continue

            call_args = stmt["expression"]["arguments"]
            if not call_args or call_args[0]["type"] != "FunctionExpression":
                continue

            for sub_stmt in call_args[0]["body"]["body"]:
                if (
                    sub_stmt["type"] != "IfStatement"
                    or sub_stmt["consequent"]["type"] != "BlockStatement"
                ):
                    continue

                for ajax_stmt in sub_stmt["consequent"]["body"]:
                    if (
                        ajax_stmt["type"] != "ExpressionStatement"
                        or ajax_stmt["expression"]["type"] != "CallExpression"
                    ):
                        continue

                    ajax_args = ajax_stmt["expression"]["arguments"]
                    if (
                        not ajax_args
                        or ajax_args[0]["type"] != "ObjectExpression"
                    ):
                        continue

                    ajax_properties = ajax_args[0].get("properties", [])
                    if (
                        len(ajax_properties) < 7
                        or "body" not in ajax_properties[6]["value"]
                    ):
                        continue

                    ajax_success = ajax_properties[6]["value"]["body"]["body"]

                    for success_stmt in ajax_success:
                        if (
                            success_stmt["type"] != "SwitchStatement"
                            or success_stmt["discriminant"]["name"]
                            != "tip_formular"
                        ):
                            continue

                        for case in success_stmt["cases"]:
                            if case["test"]["value"] != tip_formular_value:
                                continue

                            for consequent in case["consequent"]:
                                if (
                                    consequent["type"] == "VariableDeclaration"
                                    and consequent["declarations"][0]["id"][
                                        "name"
                                    ]
                                    == "days_disable"
                                ):
                                    declaration = consequent["declarations"][0]
                                    return [
                                        int(obj["value"])
                                        for obj in declaration["init"][
                                            "elements"
                                        ]
                                    ]
        return []

    async def get_disabled_weekdays(self) -> list[int, None]:
        """Get disabled weekdays."""
        html = self._programare_html

        soup = BeautifulSoup(html, "lxml")
        for i in soup.find_all("script"):
            i: Tag
            if "#tip_formular option:selected" in i.text:
                return await asyncio.to_thread(
                    self.find_days_disable, i.text, "3"
                )

    async def get_free_places_count_on_date(
        self, dt: datetime, tip_formular: int | str
    ) -> Optional[tuple[int, datetime]]:
        """Get free places count in the date and `tip_formular`."""
        if self._freest_date:
            return self._freest_date

        form = aiohttp.FormData()
        form.add_field("azi", dt.strftime("%Y-%m-%d"))
        form.add_field("tip_formular", str(tip_formular))

        @aiohttp_session(timeout=1.5, attempts=3, sleeps=(1.5, 2))
        async def inner(session: aiohttp.ClientSession):
            session._default_headers = self.headers
            async with session.post(URL_FREE_PLACES, data=form) as resp:
                try:
                    response = await resp.json(content_type=None)
                    if response.get("numar_ramase"):
                        self._freest_date = int(response["numar_ramase"]), dt
                        return self._freest_date
                except (
                    json.JSONDecodeError,
                    KeyError,
                    TypeError,
                    AttributeError,
                ):
                    return None

        return await inner()

    async def get_free_date(
        self,
        disabled_days: list[datetime],
        month: int,
        year: int = 2024,
        mode: Literal["nearest", "freest", "random"] = "random",
    ) -> Optional[datetime]:
        """Get free date of month and year by strategy (mode param)."""

        def get_dates_of_month():
            dates = []
            date_now = datetime.now()

            if date_now.month == month:
                date = datetime(year=date_now.year, month=date_now.month, day=1)

                while date_now.day != date.day:
                    date = date + timedelta(days=1)
                    dates.append(date.date())
                return dates

            if date_now.month < int(month):
                # If bigger passed month

                days = monthrange(int(year), int(month))[1]
                return [
                    datetime(year=year, month=month, day=day).date()
                    for day in range(1, days + 1)
                ]

            if date_now.month > month:
                msg = "Current month is bigger than passed month!"
                raise ValueError(msg)
            return None

        def transform_weekday(date: datetime):
            weekday = date.isoweekday()
            return weekday % 7

        dates = get_dates_of_month()
        disabled_dates = [
            datetime.strptime(d, "%Y-%m-%d").date()
            for d in self._disabled_dates_in_month
        ]
        free_dates = [
            d
            for d in dates
            if d not in disabled_dates
            and transform_weekday(d) not in disabled_days
        ]

        if mode == "nearest":
            return min(free_dates)

        if mode == "random":
            try:
                return random.choice(free_dates)
            except (IndexError, KeyError):
                return []

        if mode == "freest":
            tasks = [
                (self.get_free_places_count_on_date(date), date)
                for date in free_dates
            ]
            dates = list(
                filter(
                    lambda z: isinstance(z, tuple),
                    await asyncio.gather(*tasks, return_exceptions=True),
                )
            )
            return max(free_dates)

    async def send_registration_request(
        self,
        user_data: dict,
    ) -> str:
        """Return html response."""
        data = {
            "tip_formular": self._tip_formular,
            "nume_pasaport": user_data["Nume Pasaport"].strip(),
            "data_nasterii": user_data["Data nasterii"].strip(),
            "prenume_pasaport": user_data["Prenume Pasaport"].strip(),
            "locul_nasterii": user_data["Locul Nasterii"].strip(),
            "prenume_mama": user_data["Prenume Mama"].strip(),
            "prenume_tata": user_data["Prenume Tata"].strip(),
            "email": user_data["Adresa de email"].strip(),
            "numar_pasaport": user_data["Serie și număr Pașaport"].strip(),
            "data_programarii": self._registration_date.strftime("%Y-%m-%d"),
            "gdpr": "1",
            "honeypot": "",
            "g-recaptcha-response": await self.get_captcha_response(),
        }

        @aiohttp_session()
        async def inner(session: aiohttp.ClientSession):
            session._default_headers = self.headers
            async with session.post(SITE_URL, data=data) as resp:
                return await resp.text()

        return await inner()

    async def __aenter__(self) -> Self:
        """Please, use `async with` for prepare class for registration."""
        await self.save_disabled_month_days()

        @aiohttp_session()
        async def inner(session: aiohttp.ClientSession):
            session._default_headers = self.headers

            async with session.get(SITE_URL) as resp:
                self._programare_html = await resp.text()

        await inner()
        disabled_days = await self.get_disabled_weekdays()

        if not self._registration_date:
            self._registration_date = await self.get_free_date(
                disabled_days=disabled_days,
                mode=self._mode_to_get_registration_date,
                month=self._month_to_get_registration_date,
                year=self._year_to_get_registration_date,
            )
        return self

    async def __aexit__(self, *args) -> None:
        """Exit from class."""
        self._disabled_dates_in_month = None
        self._programare_html = None
        self._freest_date = None

    async def save_disabled_month_days(self) -> None:
        """Save disabled month days by external API."""
        form = aiohttp.FormData()
        form.add_field("tip_formular", str(self._tip_formular))
        month = (
            f"0{self._month_to_get_registration_date}"
            if len(str(self._month_to_get_registration_date)) == 1
            else self._month_to_get_registration_date
        )
        form.add_field("azi", f"{self._year_to_get_registration_date}-{month}")

        @aiohttp_session()
        async def inner(session: aiohttp.ClientSession):
            async with session.post(URL_DATES, data=form) as resp:
                response = await resp.json(content_type=None)
                self._disabled_dates_in_month = response["data"]

        await inner()
        assert isinstance(self._disabled_dates_in_month, list)

    async def registrate(
        self,
        users_data: list[dict],
    ) -> list[tuple[str, dict]]:
        """Entrypoint of class, please use with `async with` stmt.

        Parameters
        ----------
        users_data : list[dict]
            list with user_data dict.

        Returns
        -------
        list[tuple[str, dict]]
            list with respone html and user data.
        """

        async def send_request(user_data: dict):
            return (
                await self.send_registration_request(user_data=user_data),
                user_data,
            )

        tasks = [send_request(user_data=user_data) for user_data in users_data]
        return await asyncio.gather(*tasks, return_exceptions=True)

    def is_success(self, html_code: str) -> bool:
        r"""
        Return True if html response have paragraph `Felicitări`
        otherwise False.
        """
        if "<p>Felicitări!</p>" in html_code:
            return True
        return False

    def is_busy(self, html_code: str) -> bool:
        if '<p class="alert alert-danger">NU mai este loc</p>' in html_code:
            return True
        return False


SITE_TOKEN = "6LcnPeckAAAAABfTS9aArfjlSyv7h45waYSB_LwT"
SITE_URL = "https://programarecetatenie.eu/programare_online"
URL_DATES = "https://programarecetatenie.eu/status_zile"
URL_FREE_PLACES = "https://programarecetatenie.eu/status_zii"


async def registrate(dt: datetime, tip_formular: int = 4):
    logger.info(
        "year month date and tip_formular is - "
        f"{dt.year}.{dt.month}.{dt.day} and {tip_formular}."
    )
    users_data = await get_df(from_json=True)
    data = users_data.to_dict("records")

    req = RequestsRegistrator(tip_formular, dt.date())

    logger.info("Start job for check if datetime are free for appointment")
    while True:
        free_places = None
        try:
            free_places = await req.get_free_places_count_on_date(
                dt, tip_formular
            )
        except asyncio.TimeoutError:
            continue
        except Exception as e:
            logger.exception(e)

        is_busy = free_places is None

        if is_busy is False:
            logger.info(
                f"script found {free_places} free places for date: {dt}"
            )
            break

        await asyncio.sleep(random.uniform(0.5, 1))

        dt_now = datetime.now().astimezone(ZoneInfo("Europe/Moscow"))
        if dt_now.hour == 9 and dt_now.minute >= 2:
            return

    logger.info(
        f"Try to make an appointments. General count of users - {len(data)}"
    )
    async with RequestsRegistrator(
        tip_formular,
        registration_date=dt,
    ) as req:
        while True:
            dt_now = datetime.now().astimezone(ZoneInfo("Europe/Moscow"))
            try:
                results = await req.registrate(users_data=data)
                logger.info(f"Results after trying to register - {results}")
                for result in results:
                    index = results.index(result)

                    log_msg = (
                        f"{index + 1} attempt result out of "
                        f"{len(results)}: {result}."
                    )

                    if not isinstance(result, tuple):
                        log_msg += " Continue"
                        logger.info(log_msg)
                        continue

                    logger.info(log_msg)
                    html, user_data = result

                    if not isinstance(html, str):
                        continue

                    name = user_data["Nume Pasaport"]
                    msg = "successfully" if req.is_success(html) else "failed"

                    log_msg = (
                        f"registration for {name} user was "
                        f"{msg}\n---\nnot places for date {dt.day}/{dt.month}"
                        f"/{dt.year} is {req.is_busy(html)}\n---\n---"
                        f"tip formular is {tip_formular}\n---"
                    )
                    logger.info(log_msg)

                    async with aiofiles.open(f"user_{name}.html", "w") as f:
                        await f.write(html)

            except Exception as e:
                logger.exception(e)
            else:
                break
            finally:
                if dt_now.hour == 9 and dt_now.minute >= 2:
                    break


@aiohttp_session()
async def main(session: aiohttp.ClientSession):
    year = 2024
    month = 10
    day = datetime.now().astimezone(ZoneInfo("Europe/Moscow")).day
    try:
        async with session.get(SITE_URL) as resp:
            soup = BeautifulSoup(await resp.text(), "lxml")

        tip_formular = int(
            soup.find("select", id="tip_formular").find(
                "option", string=re.compile(".*ART.* 10")
            )["value"]
        )
    except Exception as e:
        logger.exception(e)
        tip_formular = 4

    results = await registrate(
        datetime(year=year, month=month, day=day), tip_formular
    )
    logger.info(f"Results: {results}")


if __name__ == "__main__":
    asyncio.run(main())
