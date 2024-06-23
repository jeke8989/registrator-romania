import asyncio
from datetime import date, datetime
import json
import random
import string
from typing import Optional
from zoneinfo import ZoneInfo

import aiofiles
from loguru import logger
import ua_generator
import aiohttp
from pypasser import reCaptchaV3

from registrator_romania.proxy import aiohttp_session


SITE_TOKEN = "6LcnPeckAAAAABfTS9aArfjlSyv7h45waYSB_LwT"
BASE_URL = "https://programarecetatenie.eu"
URL_GENERAL = f"{BASE_URL}/programare_online"
URL_PLACES = f"{BASE_URL}/status_zii"
URL_DATES = f"{BASE_URL}/status_zile"
CAPTCHA_URL = (
    "https://www.google.com/recaptcha/api2/anchor?ar=1"
    f"&k={SITE_TOKEN}&co=aHR0cHM6Ly9wcm9ncmFtYXJlY2V0YX"
    "RlbmllLmV1OjQ0Mw..&hl=ru&v=DH3nyJMamEclyfe-nztbfV8S"
    "&size=invisible&cb=ulevyud5loaq"
)


def get_headers():
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
    }
    for key, value in ua.headers.get().items():
        headers[key] = value

    return headers


async def get_captcha_response() -> str:
    """Async get and return `g-recaptcha-response` field."""
    return await asyncio.to_thread(reCaptchaV3, CAPTCHA_URL)


@aiohttp_session()
async def check_places(
    session: aiohttp.ClientSession, dt: date, tip: int
) -> Optional[tuple[int, date]]:
    form = aiohttp.FormData()
    form.add_field("azi", dt.strftime("%Y-%m-%d"))
    form.add_field("tip_formular", str(tip))

    session._default_headers = get_headers()
    async with session.post(URL_PLACES, data=form) as resp:
        try:
            response = await resp.json(content_type=None)
            if response.get("numar_ramase"):
                return int(response["numar_ramase"]), dt
        except (
            json.JSONDecodeError,
            KeyError,
            TypeError,
            AttributeError,
        ):
            return None


async def registrate(users_data: list[dict], tip_formular: int, reg_dt: date):
    # Request body
    # {
    #     "tip_formular": "3",
    #     "nume_pasaport": "jvggcjgcg",
    #     "data_nasterii": "2020-06-18",
    #     "prenume_pasaport": "hfchfchf",
    #     "locul_nasterii": "jhvjgvjg",
    #     "prenume_mama": "tgcgdx",
    #     "prenume_tata": "dgcgxgd",
    #     "email": "ghvgxd@gmail.com",
    #     "numar_pasaport": "U545354",
    #     "data_programarii": "2024-10-16",
    #     "gdpr": "1",
    #     "honeypot": "",
    #     "g-recaptcha-response": "03AFcWeA5TPbxUp8c9ZAkwNIreC1H47-aWrqdINKi6v7Thi3uOPmtEeBUxiLgzY5-kvQ8g6dYHEamVx9zq7D6q7rcKl7qIC_ZsC1oElYaH19q0MPpgUHbrK6g3ZJkAqvqIGoGhJXVoFDcCxTT7W3d9vRmMEI7QaOuNTGxrmgbIPS6z7RdOjFwSJ4n4HqWmXq2vCJWyOlwXL9jC-535vYnCEdZek76BiR1F_SCPUdCdXs3kHdXhDQLVlSl9TEBIFmrVB3Z5TS7BoD0IXWg9oBBpjc1bpZ1kaeIZrTgMSDqI6WcWWJ4CyAB3FHYbm-68pabrsBppUl68zfsUcQkOv3qEj3ciMfKsqk8OK6kpqPcWk50DdQy3Ysu50ED6XpDLdKwDRa5_d8vNhn52noe8dxdLhQYiLS7xPIB_D6lQlrEfU8mI-Vslja25hpUJODXlqArN0SlfVAzH7bQiSP7UzSAeMEOzQAWex_G5fD2elt7pGXCtvrFHUwmUy7L4yc0bYoqyJ5CQqLR6t0_R72Bv-IGQ1NI6IlAam5vnPJNpANgkVSnSaAPV_rRBPZXqawGKmrIwsYeSmVCHtG-SPd6pz_L_6IVGaNNov9PsJXKRuxjcJBLuaakkQJgIfYQiQmWIzzC50uaZOTi8mgSx8C6a71z23U2P3HiD5Bao_Blagy0UJ12c9dNXO0uPzJlYlDalHF29ULLx6QVAa_s0",
    # }

    @aiohttp_session()
    async def reg(session: aiohttp.ClientSession, user_data: dict):
        session._default_headers = get_headers()
        
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
            "data_programarii": reg_dt.strftime("%Y-%m-%d"),
            "gdpr": "1",
            "honeypot": "",
            "g-recaptcha-response": await get_captcha_response(),
        }

        async with session.post(URL_GENERAL, data=data) as resp:
            return (await resp.text(), user_data)

    tasks = []
    for user_data in users_data:
        tasks.append(reg(user_data))

    return await asyncio.gather(*tasks, return_exceptions=True)


def get_dt(tz: Optional[ZoneInfo] = None) -> datetime:
    if not tz:
        tz = ZoneInfo("Europe/Moscow")

    return datetime.now().astimezone(tz=tz)


def is_success(html_code: str) -> bool:
    r"""
    Return True if html response have paragraph `Felicitări`
    otherwise False.
    """
    if "<p>Felicitări!</p>" in html_code:
        return True
    return False


def is_busy(html_code: str) -> bool:
    if '<p class="alert alert-danger">NU mai este loc</p>' in html_code:
        return True
    return False


def get_users_data():
    keys = [
        "Prenume Pasaport",
        "Nume Pasaport",
        "Data nasterii",
        "Locul naşterii",
        "Prenume Mama",
        "Prenume Tata",
        "Adresa de email",
        "Serie și număr Pașaport",
    ]
    with open("users.txt") as f:
        data = f.read()

    objs = []
    for values in data.split("\n\n"):
        obj = {}
        for k, v in zip(keys, values.split("\n")):
            obj[k] = v.split(":")[-1].strip()
        obj["Adresa de email"] = obj["Adresa de email"].lower()
        objs.append(obj)

    return objs


async def main():
    dt_now = get_dt()
    dt = date(dt_now.year, 10, dt_now.day)
    # dt = date(dt_now.year, 10, 17)

    # 4 - articolul 10. 3 for artcolul 11
    tip_formular = 4

    def random_string(n: int = 5):
        return "".join(
            random.choice(string.ascii_uppercase + string.digits)
            for _ in range(n)
        )

    users_data = [
        {
            "Nume Pasaport": f"P{random_string(5)}IR",
            "Prenume Pasaport": f"{random_string(7)}DRI",
            "Data nasterii": f"199{random.randint(0, 9)}-10-1{random.randint(0, 9)}",
            "Locul naşterii": f"SI{random_string(3)}RI",
            "Prenume Mama": f"REC{random_string(3)}YE",
            "Prenume Tata": "SABRI",
            "Adresa de email": f"{"".join(random.choice(string.ascii_uppercase) for _ in range(10))}@gmail.com",
            "Serie și număr Pașaport": f"U{random.randint(10_000_000, 10_999_999)}",
        }
        for _ in range(40)
        # for nume, prenume, bdt, locul, mama, tata, pspt in [
        #     [
        #         "PAMIR",
        #         "KADRI",
        #         "1984-10-21",
        #         "SILIVRI",
        #         "RECEBIYE",
        #         "SABRI",
        #         "U32965790",
        #     ],
        #     [
        #         "RAMIL",
        #         "KUNAN",
        #         "1986-5-15",
        #         "SILIVRI",
        #         "RECEBYE",
        #         "SABRI",
        #         "S20769456",
        #     ],
        # ]
    ]
    users_data = get_users_data()

    while True:
        try:
            free_places = await check_places(dt, tip_formular)
        except Exception as e:
            logger.exception(e)
        else:
            not_places = free_places is None

            if not_places is False:
                logger.info(
                    f"script found {free_places} free places for date: {dt}"
                )
                break
            await asyncio.sleep(random.uniform(0.5, 1))

        finally:
            if get_dt().hour == 9 and get_dt().minute >= 2:
                return

    logger.info(
        f"Try to make an appointments. General count of users - {len(users_data)}"
    )

    while True:
        dt_now = get_dt()
        try:
            results = await registrate(users_data, tip_formular, dt)

            for result in results:
                if not isinstance(result, tuple):
                    continue

                html, user_data = result

                if not isinstance(html, str):
                    continue

                name = user_data["Nume Pasaport"]
                msg = "successfully" if is_success(html) else "failed"

                log_msg = (
                    f"registration for {name} user was "
                    f"{msg}\n---\nnot places for date {dt.day}/{dt.month}"
                    f"/{dt.year} is {is_busy(html)}\n---\n---"
                    f"tip formular is {tip_formular}\n---"
                )
                logger.info(log_msg)

                async with aiofiles.open(f"user_{name}.html", "w") as f:
                    await f.write(html)

                if is_success(html) is False:
                    raise Exception

        except Exception as e:
            logger.exception(e)

        else:
            return


if __name__ == "__main__":
    asyncio.run(main())
