from __future__ import annotations

import asyncio
import os
import random
import re
import subprocess
from datetime import datetime
from typing import TYPE_CHECKING, Callable, Generator, Literal

from bs4 import BeautifulSoup, Tag
from loguru import logger
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from registrator_romania.bot import send_screenshot_to_chat
from registrator_romania.google_spread import get_df

if TYPE_CHECKING:
    from pandas import Series

URL = "https://programarecetatenie.eu/programare_online"


class Calendar:
    """Simple API to find dates from date picker in HTML."""

    def __init__(self, soup: BeautifulSoup) -> None:
        self._soup = soup
        self._enabled_days = list(self._soup.find_all("td", class_="day"))

    def iter_available_days(
        self,
    ) -> Generator[tuple[Tag, datetime], None, None]:
        """Iterate available days to appointment.

        Yields
        ------
        Generator[tuple[Tag, datetime], None, None]
            (bs4 tag, datetime).

        Examples
        --------
        >>> # Suppose you have already created an instance of this class
        >>> for tag, dt in calendar.iter_available_days():
        ...     tag: bs4.Tag
        ...     dt: datetime

        """
        for day in self._enabled_days:
            timestamp = int(day["data-date"][:-3])
            dt = datetime.fromtimestamp(timestamp)
            if day["class"] == ["day"]:
                yield day, dt


def error_attempts(attempts: int = 5):
    def wrapper(f: Callable):
        async def inner(*args, **kwargs):
            nonlocal attempts
            try:
                return await f(*args, **kwargs)
            except Exception as e:
                logger.exception(e)
                if attempts:
                    attempts -= 1
                    return await inner(*args, **kwargs)
                raise

        return inner

    return wrapper


class ProgramareCetatenie:
    def __init__(self) -> None:
        self.plw: Playwright | None = None
        self.context: BrowserContext | None = None
        self.browser: Browser | None = None

    async def _create_context(self) -> BrowserContext:
        return await self.browser.new_context(
            user_agent=HEADERS["User-Agent"], extra_http_headers=HEADERS
        )

    async def __aenter__(self):
        self.plw = await async_playwright().start()
        self.browser = await self.plw.chromium.launch(headless=False)
        self.context = await self._create_context()
        return self

    async def __aexit__(self, *args):
        await self.browser.close()
        await self.plw.stop()

    async def get_available_months(
        self,
        page: Page | None = None,
        action: Literal["close", "return"] = "return",
    ) -> list[Tag]:
        """Get available month to appointment."""
        if not page:
            page = await self.context.new_page()
            await page.goto(URL)

        await page.click(
            "//div[@class='datepicker-days']//th[@class='datepicker-switch']"
        )

        page_text = await page.content()
        soup = BeautifulSoup(page_text, "html.parser")
        available_months = [
            t
            for t in soup.find_all("span", class_="month")
            if len(t.get("class", [])) == 1
            or t.get("class", [])[1] == "focused"
        ]
        assert available_months

        if action == "return":
            await page.click(
                "//span[contains(@class, 'month') "
                "and contains(@class, 'focused')]"
            )
        elif action == "close":
            await page.close()

        return available_months

    async def fill_inputs(
        self, page: Page, row: Series, test: bool = False
    ) -> None:
        """Fill needed inputs in page."""
        first_name = row["Nume Pasaport"]
        date_of_birthday = row["Data nasterii"]
        last_name = row["Prenume Pasaport"]
        birthday_place = row["Locul Nasterii"]
        mother_name = row["Prenume Mama"]
        father_name = row["Prenume Tata"]
        email = row["Adresa de email"]
        series_passport = row["Serie și număr Pașaport"]

        if test:
            first_name = "".join(random.sample(first_name, len(first_name)))
            last_name = "".join(random.sample(last_name, len(last_name)))
            birthday_place = "".join(
                random.sample(birthday_place, len(birthday_place))
            )
            mother_name = "".join(random.sample(mother_name, len(mother_name)))
            father_name = "".join(random.sample(father_name, len(father_name)))
            email = "".join(random.sample(email, len(email)))
            series_passport = "".join(
                random.sample(series_passport, len(series_passport))
            )

        await page.type("//input[@id='nume_pasaport']", first_name)
        await page.type("//input[@id='data_nasterii']", date_of_birthday)
        await page.type("//input[@id='prenume_pasaport']", last_name)
        await page.type("//input[@id='locul_nasterii']", birthday_place)
        await page.type("//input[@id='prenume_mama']", mother_name)
        await page.type("//input[@id='prenume_tata']", father_name)
        await page.type("//input[@id='email']", email)
        await page.type("//input[@id='numar_pasaport']", series_passport)

    async def _select_articolul(self, page: Page, num: int) -> None:
        # Open dropdown with a list of articoluls.
        xpath_dropdown = "//span[@id='select2-tip_formular-container']"
        await page.click(xpath_dropdown)

        # Select needed artcolul
        xpath_articolul = (
            "//ul[@id='select2-tip_formular-results']//"
            f"li[contains(text(), 'ART. {num}') "
            f"or contains(text(), 'ART {num}')]"
        )
        await page.click(xpath_articolul)

    async def select_month(self, needed_month: str, page: Page):
        months = await self.get_available_months(page)
        logger.info(f"available month - {months}")

        for month in months:
            # Find needed month
            if month.text != needed_month:
                continue

            logger.info("change month...")
            await page.click(
                "//div[@class='datepicker-days']"
                "//th[@class='datepicker-switch']"
            )
            await page.click(
                f"//span[contains(@class, 'month') and text()='{month.text}']"
            )

            await page.wait_for_selector("//div[@class='datepicker-days']")
            # Wait while date picker is loads
            await page.wait_for_selector(
                '//div[@class="loading"]', state="hidden"
            )

            return

    async def select_day(self, needed_day: int, page: Page) -> bool:
        page_text = await page.content()
        soup = BeautifulSoup(page_text, "html.parser")
        cal = Calendar(soup)

        for tag, dt in cal.iter_available_days():
            tag: Tag
            dt: datetime

            # Wait for a needed day
            if dt.day != needed_day:
                continue

            # Select needed day
            await page.click(f"//td[@data-date='{tag["data-date"]}']")
            return True
        return False

    async def click_on_checkbox(self, page: Page):
        # Click on checkbox before finish
        await page.click(
            "//input[@class='form-check-input' and @type='checkbox']"
        )

    async def click_registration(self, page: Page):
        # Wait while button is hidden
        await page.wait_for_selector(
            "//div[@id='spinner_button' and @class='spinner-border']",
            state="hidden",
        )
        # Click on the finish button
        await page.get_by_text(re.compile("Transmite.*")).click()
        await asyncio.sleep(4)
        html = await page.content()
        logger.info(f"Press finish button. HTML:\n---\n{html}")

        # Wait for success message
        await page.get_by_text(re.compile(r"Felicitări!.*")).wait_for(
            timeout=60000
        )

    @error_attempts(3)
    async def make_an_appointment(self, row: Series) -> None:
        """Make an appointment."""
        em = row["Adresa de email"]
        logger.info(f"start work of row = {em}. open page...")
        page = await self.context.new_page()
        await page.goto(URL)
        self.context.set_default_timeout(60000)

        logger.info(f"select needed articolul...\n {em}")
        num = 11
        await self._select_articolul(page=page, num=num)

        logger.info(f"fill inputs... {em}")
        await self.fill_inputs(page, row, test=True)
        logger.info(f"filling inputs successfully {em}")

        month = "Oct"
        logger.info(f"try to switch month on {month} for {em}")
        await self.select_month(needed_month=month, page=page)
        logger.info(f"changing month successfully on {month} for {em}")

        day = 2
        logger.info(f"try to select day on {day} of {month} for {em}")
        assert await self.select_day(day, page=page)
        logger.info(f"selected day on {day} of {month} for {em} successfully")

        logger.info(f"try to click on checkbox for {em}")
        await self.click_on_checkbox(page=page)
        logger.info(f"clicked on checkbox for {em} successfully")

        logger.info(f"click on finish button for {em}")
        await self.click_registration(page=page)
        logger.info(f"clicked on finish button for {em} successfully")

        # Make a screenshot in memory
        dt = datetime.now()
        path = f"screenshots/{dt}_{em}.png"
        screenshot = await page.screenshot(full_page=True, path=path)
        logger.info(f"Make a screenshot to {path}")
        # Send to telegram chat
        await send_screenshot_to_chat(screenshot)
        del screenshot


HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "sec-ch-ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Linux"',
}


async def wait_for_available_day(programare: ProgramareCetatenie):
    """Wait for available day."""
    while True:
        try:
            page = await programare.context.new_page()
            await programare.select_month("Oct", page)
            assert await programare.select_day(2, page)
        except Exception as err:
            logger.exception(err)
            dt = datetime.now()
            if dt.hour >= 9 and dt.minute >= 10:
                return
        else:
            return


async def main() -> None:
    """Entrypoint."""
    async with ProgramareCetatenie() as automator:
        await wait_for_available_day(automator)
        # page = await automator.context.new_page()
        # await page.goto(URL)
        # ...

        async def work(row: Series):
            try:
                await automator.make_an_appointment(row)
            except Exception as exc:
                logger.exception(exc)
                return False
            else:
                return True

        tasks = []
        df = await get_df()
        for index, row in df.iterrows():
            if len(tasks) < 1:
                logger.info(f"Create task for user {row}")
                tasks.append(work(row))

        result = await asyncio.gather(*tasks, return_exceptions=True)
        logger.info(f"{len(tasks)} runned. The result\n---\n{result}")


if __name__ == "__main__":
    process = None
    if "DISPLAY" not in os.environ:
        os.environ["DISPLAY"] = ":99"
        process = subprocess.Popen(
            ["Xvfb", ":99", "-screen", "0", "1024x768x16"]
        )

    asyncio.run(main())

    if process:
        process.kill()
