import asyncio
import random
import string

import aiohttp
import requests
import ua_generator
from bs4 import BeautifulSoup
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


async def get_date():
    headers = {
        "Accept": "*/*",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
        "Connection": "keep-alive",
        "Content-Type": "multipart/form-data; boundary=----WebKitFormBoundaryBAFqUEJZBFiTrpGE",
        # 'Cookie': 'ADC_CONN_539B3595F4E=CDCB981DB7B86020AFD253C8C03B3BBC0E62E531671B481654F4529FFAB0BD45669E66157C80011F; ADC_REQ_2E94AF76E7=16C0E6F3593A4DE3DB6460302FCAD0D31FB5BF91F2EA2A0900D80EBF6E50C39870F691148C17265C; cetatenie_session=d5d4a5affd59e0d01a0dd86d4dca8d01b90f586d',
        "Origin": "https://programarecetatenie.eu",
        "Referer": "https://programarecetatenie.eu/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "sec-ch-ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Linux"',
    }

    files = {
        "azi": "2024-06",
        "tip_formular": "3",
    }

    response = requests.post(
        "https://programarecetatenie.eu/status_zile",
        headers=headers,
        files=files,
    )
    print(response.content)


@aiohttp_session()
async def work(session: aiohttp.ClientSession):
    def random_str(n: int = 15):
        return "".join(
            random.choices(string.ascii_uppercase + string.digits, k=n)
        )

    r = RequestsRegistrator()

    session._default_headers = r.headers
    # async with session.get(URL) as resp:
    # html = await resp.text()
    with open("programare.html") as f:
        html = f.read()

    main_soup = BeautifulSoup(html, "lxml")
    select_tag = main_soup.find("select", id="tip_formular")
    tip_formulars = select_tag.find_all("option")
    needed_tips = [t for t in tip_formulars if t.text[-2:] == "11"]
    tip_formular = random.choice(needed_tips)["value"]

    grecaptcha_token = await r.do_async_request()

    data = {
        "tip_formular": tip_formular,
        "nume_pasaport": random_str(),
        "data_nasterii": "2003-04-17",
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
    response = requests.post(
        "https://programarecetatenie.eu/programare_online",
        headers=r.headers,
        data=data,
    )
    print(response.text)


async def main():
    # await work()
    await get_date()


if __name__ == "__main__":
    asyncio.run(main())
