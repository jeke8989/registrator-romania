import asyncio
import json
import random
import re
import string
from calendar import monthrange
from datetime import datetime, timedelta
from typing import Literal, Optional

import aiofiles
import aiohttp
import pyjsparser
import ua_generator
from bs4 import BeautifulSoup, Tag
from fake_useragent import UserAgent
from pypasser import reCaptchaV3

from registrator_romania.proxy import aiohttp_session


class RequestsRegistrator:
    def __init__(self) -> None:
        self._captcha_url = (
            "https://www.google.com/recaptcha/api2/anchor?ar=1"
            f"&k={SITE_TOKEN}&co=aHR0cHM6Ly9wcm9ncmFtYXJlY2V0YX"
            "RlbmllLmV1OjQ0Mw..&hl=ru&v=DH3nyJMamEclyfe-nztbfV8S"
            "&size=invisible&cb=ulevyud5loaq"
        )

    @property
    def headers(self):
        ua = ua_generator.generate()
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
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

    async def do_async_request(self):
        return await asyncio.to_thread(reCaptchaV3, self._captcha_url)

    def do_request(self):
        return reCaptchaV3(self._captcha_url)


headers = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
    # "Cache-Control": "max-age=0",
    # "Connection": "keep-alive",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://programarecetatenie.eu",
    "Referer": "https://programarecetatenie.eu/programare_online",
    # "Sec-Fetch-Dest": "document",
    # "Sec-Fetch-Mode": "navigate",
    # "Sec-Fetch-Site": "same-origin",
    # "Upgrade-Insecure-Requests": "1",
    "User-Agent": UserAgent().random,
    "sec-ch-ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Linux"',
}

SITE_TOKEN = "6LcnPeckAAAAABfTS9aArfjlSyv7h45waYSB_LwT"


headers = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
    "Cache-Control": "max-age=0",
    "Connection": "keep-alive",
    "Content-Type": "application/x-www-form-urlencoded",
    # 'Cookie': 'ADC_CONN_539B3595F4E=429A4D726EA20BE51E6B7F3A4020B8F4DB76F5171EB0BAD79BACECC0617A62D67BAA605B1D28043C; ADC_REQ_2E94AF76E7=B5AADBAE15CECCCF219998D18B81F0837233F6F700E76BC475C7B2331CB63BD7D5907EF819F710A0; cetatenie_session=4b0f76e0e66e05f83702a3849e0226792dab0131',
    "Origin": "https://programarecetatenie.eu",
    "Referer": "https://programarecetatenie.eu/programare_online",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": UserAgent().random,
    "sec-ch-ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Linux"',
}


@aiohttp_session()
async def get_date(
    session: aiohttp.ClientSession,
    disabled_days: list[datetime],
    month: int,
    tip_formular: int,
    year: int = 2024,
    mode: Literal["nearest", "random"] = "random",
) -> Optional[datetime]:
    month = f"0{month}" if len(str(month)) == 1 else month

    form = aiohttp.FormData()
    form.add_field("azi", f"{year}-{month}")
    form.add_field("tip_formular", str(tip_formular))

    async with session.post(
        "https://programarecetatenie.eu/status_zile", data=form
    ) as response:
        text = await response.text()
        async with aiofiles.open("dates.json", "w") as f:
            await f.write(text)

    # async with aiofiles.open("dates.json") as f:
    #     text = await f.read()

    month = int(month)

    def get_dates_of_month():
        dates = []
        date_now = datetime.now()

        if date_now.month == month:
            date = datetime(year=date_now.year, month=date_now.month, day=1)

            while date_now.day != date.day:
                date = date + timedelta(days=1)
                dates.append(date.date())
            return dates

        if date_now.month < month:
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
        for d in json.loads(text)["data"]
    ]
    available_dates = [
        d
        for d in dates
        if d not in disabled_dates and transform_weekday(d) not in disabled_days
    ]
    if mode == "nearest":
        return min(available_dates)
    if mode == "random":
        return random.choice(available_dates)


@aiohttp_session()
async def work(
    session: aiohttp.ClientSession, date: datetime, tip_formular: int
):
    def random_str(n: int = 15):
        return "".join(random.choices(string.ascii_uppercase, k=n))

    r = RequestsRegistrator()
    session._default_headers = r.headers

    grecaptcha_token = await r.do_async_request()

    data = {
        "tip_formular": tip_formular,
        "nume_pasaport": random_str(),
        "data_nasterii": date.strftime("%Y-%m-%d"),
        "prenume_pasaport": random_str(7),
        "locul_nasterii": random_str(4),
        "prenume_mama": random_str(6),
        "prenume_tata": random_str(5),
        "email": f"{random_str(7)}@gmail.com",
        "numar_pasaport": "".join(
            [random.choice(string.digits) for _ in range(10)]
        ),
        "data_programarii": "2024-07-23",
        "gdpr": "1",
        "honeypot": "",
        "g-recaptcha-response": grecaptcha_token,
    }
    async with session.post(SITE_URL, data=data) as resp:
        return await resp.text()
    # response = requests.post(
    #     SITE_URL,
    #     headers=r.headers,
    #     data=data,
    # )
    # print(response.text)


SITE_URL = "https://programarecetatenie.eu/programare_online"


def find_days_disable(js_code, tip_formular_value):
    parser = pyjsparser.PyJsParser()
    parsed_code = parser.parse(js_code)

    for stmt in parsed_code["body"]:
        if (
            stmt["type"] == "ExpressionStatement"
            and stmt["expression"]["type"] == "CallExpression"
        ):
            for sub_stmt in stmt["expression"]["arguments"][0]["body"]["body"]:
                if (
                    sub_stmt["type"] == "IfStatement"
                    and sub_stmt["consequent"]["type"] == "BlockStatement"
                ):
                    for ajax_stmt in sub_stmt["consequent"]["body"]:
                        if (
                            ajax_stmt["type"] == "ExpressionStatement"
                            and ajax_stmt["expression"]["arguments"][0]["type"]
                            == "ObjectExpression"
                        ):
                            ajax_success = ajax_stmt["expression"]["arguments"][
                                0
                            ]["properties"][6]["value"]["body"]["body"]
                            for success_stmt in ajax_success:
                                if (
                                    success_stmt["type"] == "SwitchStatement"
                                    and success_stmt["discriminant"]["name"]
                                    == "tip_formular"
                                ):
                                    for case in success_stmt["cases"]:
                                        if (
                                            case["test"]["value"]
                                            == tip_formular_value
                                        ):
                                            for consequent in case[
                                                "consequent"
                                            ]:
                                                if (
                                                    consequent["type"]
                                                    == "VariableDeclaration"
                                                    and consequent[
                                                        "declarations"
                                                    ][0]["id"]["name"]
                                                    == "days_disable"
                                                ):
                                                    return [
                                                        int(obj["value"])
                                                        for obj in consequent[
                                                            "declarations"
                                                        ][0]["init"]["elements"]
                                                    ]
    return []


URL_DATES = "https://programarecetatenie.eu/status_zile"


@aiohttp_session()
async def get_disabled_days(session: aiohttp.ClientSession):
    r = RequestsRegistrator()
    session._default_headers = r.headers

    # async with session.get(SITE_URL) as resp:
    #     html = await resp.text()

    async with aiofiles.open("programare.html") as f:
        html = await f.read()

    soup = BeautifulSoup(html, "lxml")
    for i in soup.find_all("script"):
        i: Tag
        if "#tip_formular option:selected" in i.text:
            return find_days_disable(i.text, "3")


async def do(i):
    async with aiofiles.open("programare.html") as f:
        html = await f.read()

    main_soup = BeautifulSoup(html, "lxml")
    select_tag = main_soup.find("select", id="tip_formular")
    tip_formulars = select_tag.find_all("option")
    needed_tips = [t for t in tip_formulars if t.text[-2:] == "11"]
    tip_formular = random.choice(needed_tips)["value"]

    ddays = await get_disabled_days()
    available_date = await get_date(ddays, 7, tip_formulars, 2024, "random")
    res = await work(available_date, tip_formular)

    if isinstance(res, str) and re.findall("Felicitări!", res):
        print("SUCCESS")
    else:
        print("FAIL")

    async with aiofiles.open(f"{i}.html", "w") as f:
        await f.write(res)


async def main():
    start = datetime.now()
    tasks = [do(i) for i in range(1, 11)]
    result = await asyncio.gather(*tasks, return_exceptions=False)
    print(f"\n---\nRESULT OF {datetime.now() - start}\n---\n{result}")


if __name__ == "__main__":
    asyncio.run(main())
