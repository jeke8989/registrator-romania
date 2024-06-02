import bs4
import requests

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
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "sec-ch-ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Linux"',
}


def main():
    data = {
        "tip_formular": "3",
        "nume_pasaport": "mbvgv",
        "data_nasterii": "2003-04-17",
        "prenume_pasaport": "hhvg hvhf",
        "locul_nasterii": "hvgjv",
        "prenume_mama": "exdxgd",
        "prenume_tata": "dgxgdx",
        "email": "hbbhm@gmail.com",
        "numar_pasaport": "02354354",
        "data_programarii": "2024-07-23",
        "gdpr": "1",
        "honeypot": "",
        "g-recaptcha-response": "",
    }

    response = requests.post(
        "https://programarecetatenie.eu/programare_online",
        headers=headers,
        data=data,
    )
    print(response)


def get_recaptcha_response():
    resp_html = requests.get("https://programarecetatenie.eu")
    print(resp_html)
    s = bs4.BeautifulSoup(resp_html.text, "html.parser")

    params = s.find("//iframe[@title='reCAPTCHA']")["src"]
    print(params)


get_recaptcha_response()
