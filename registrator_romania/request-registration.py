import asyncio
from calendar import monthrange
from datetime import datetime, timedelta
import json
from pprint import pprint
import random
import string

import aiohttp
import pyjsparser
import requests
import ua_generator
import esprima
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
async def get_date(session: aiohttp.ClientSession, disabled_days: list[datetime], month: int, tip_formular: int, year: int = 2024):
    r = RequestsRegistrator()
    month = f"0{month}" if len(str(month)) == 1 else month

    form = aiohttp.FormData()
    form.add_field('azi', f"{year}-{month}")
    form.add_field('tip_formular', str(tip_formular))
    
    # async with session.post(
    #     'https://programarecetatenie.eu/status_zile', 
    #     data=form
    # ) as response:
    #     text = await response.text()
    #     with open("dates.json", "w") as f:
    #         f.write(text)
        
    with open("dates.json") as f:
        text = f.read()
        
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
        
        elif date_now.month < month:
            # If bigger passed month

            days = monthrange(year, month)[1]
            return [
                datetime(year=year, month=month, day=day).date()
                for day in range(1, days + 1)
            ]
        
        elif date_now.month > month:
            raise ValueError("Current month is bigger than passed month!")
    
    dates = get_dates_of_month()
    disabled_dates = [datetime.strptime(d, "%Y-%m-%d").date() for d in json.loads(text)["data"]]
    available_dates = []
    
    for date in dates:
        if date not in disabled_dates:
            available_dates.append(date)
    
    return available_dates


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


def extract_days_disable(js_code):
    parsed_code = esprima.parseScript(js_code)
    days_disable_dict = {}
    for node in parsed_code.body:
        if isinstance(node, esprima.nodes.FunctionDeclaration) and node.id.name == 'success':
            for inner_node in node.body.body:
                if isinstance(inner_node, esprima.nodes.SwitchStatement):
                    for case in inner_node.cases:
                        case_value = case.test.value
                        for consequent in case.consequent:
                            if isinstance(consequent, esprima.nodes.VariableDeclaration):
                                for declaration in consequent.declarations:
                                    if declaration.id.name == 'days_disable':
                                        days_disable_values = [element.value for element in declaration.init.elements]
                                        days_disable_dict[case_value] = days_disable_values
    return days_disable_dict

def find_days_disable(js_code, tip_formular_value):
    parser = pyjsparser.PyJsParser()
    parsed_code = parser.parse(js_code)
    
    for stmt in parsed_code['body']:
        if stmt['type'] == 'ExpressionStatement' and stmt['expression']['type'] == 'CallExpression':
            for sub_stmt in stmt['expression']['arguments'][0]['body']['body']:
                if sub_stmt['type'] == 'VariableDeclaration' and sub_stmt['declarations'][0]['id']['name'] == 'tip_formular':
                    for ajax_stmt in stmt['expression']['arguments'][0]['body']['body']:
                        if ajax_stmt['type'] == 'ExpressionStatement' and ajax_stmt['expression']['type'] == 'CallExpression':
                            ajax_success = ajax_stmt['expression']['arguments'][0]['properties'][5]['value']['body']['body']
                            for success_stmt in ajax_success:
                                if success_stmt['type'] == 'SwitchStatement' and success_stmt['discriminant']['name'] == 'tip_formular':
                                    for case in success_stmt['cases']:
                                        if case['test']['value'] == tip_formular_value:
                                            for consequent in case['consequent']:
                                                if consequent['type'] == 'VariableDeclaration' and consequent['declarations'][0]['id']['name'] == 'days_disable':
                                                    return consequent['declarations'][0]['init']['elements']
    return None


async def get_disabled_days():
    with open("programare.html") as f:
        html = f.read()
    soup = BeautifulSoup(html, "lxml")
    for i in soup.find_all("script"):
        i: Tag
        if "#tip_formular option:selected" in i.text:
            res = find_days_disable(i.text, '3')
            pprint(res)


async def main():
    # await work()
    await get_disabled_days()
    # await get_date(7, 3)


if __name__ == "__main__":
    asyncio.run(main())
