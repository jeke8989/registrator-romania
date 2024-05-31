from __future__ import annotations

import asyncio
import os
import random
import re
import subprocess
from datetime import datetime
from typing import TYPE_CHECKING, Generator

from bs4 import BeautifulSoup, Tag
from loguru import logger
from playwright.async_api import (
    BrowserContext,
    Page,
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
        self._enabled_days = [
            t
            for t in self._soup.find_all("td", class_="day")
            if len(t.get("class", [])) == 1
        ]

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
            if "disabled" in day["class"]:
                continue
            yield day, dt


async def get_available_months(
    switch_month_btn_xpath: str, page: Page
) -> list[Tag]:
    """Get available month to appointment."""
    await page.click(switch_month_btn_xpath)
    page_text = await page.content()
    soup = BeautifulSoup(page_text, "html.parser")
    available_months = [
        t
        for t in soup.find_all("span", class_="month")
        if len(t.get("class", [])) == 1 or t.get("class", [])[1] == "focused"
    ]
    assert available_months

    await page.click(
        "//span[contains(@class, 'month') and contains(@class, 'focused')]"
    )
    return available_months


async def fill_inputs(page: Page, row: Series, test: bool = False) -> None:
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
        random.shuffle(first_name)
        random.shuffle(last_name)
        random.shuffle(father_name)
        random.shuffle(mother_name)
        random.shuffle(birthday_place)
        random.shuffle(date_of_birthday)
        random.shuffle(email)
        random.shuffle(series_passport)

    await page.type("//input[@id='nume_pasaport']", first_name)
    await page.type("//input[@id='data_nasterii']", date_of_birthday)
    await page.type("//input[@id='prenume_pasaport']", last_name)
    await page.type("//input[@id='locul_nasterii']", birthday_place)
    await page.type("//input[@id='prenume_mama']", mother_name)
    await page.type("//input[@id='prenume_tata']", father_name)
    await page.type("//input[@id='email']", email)
    await page.type("//input[@id='numar_pasaport']", series_passport)


async def make_an_appointment(context: BrowserContext, row: Series) -> None:
    """Make an appointment."""
    page = await context.new_page()
    await page.goto(URL)

    # Open dropdown with a list of articoluls.
    xpath_dropdown = "//span[@id='select2-tip_formular-container']"
    await page.click(xpath_dropdown)

    # Select needed artcolul
    num = 10
    xpath_articolul = (
        "//ul[@id='select2-tip_formular-results']//"
        f"li[contains(text(), 'ART. {num}') or contains(text(), 'ART {num}')]"
    )
    await page.click(xpath_articolul)

    await fill_inputs(page, row, test=True)

    switch_month_btn_xpath = (
        "//div[@class='datepicker-days']//th[@class='datepicker-switch']"
    )
    for month in await get_available_months(switch_month_btn_xpath, page):
        # Find needed month
        if month.text != "Oct":
            continue

        await page.click(switch_month_btn_xpath)
        await page.click(
            f"//span[contains(@class, 'month') and text()='{month.text}']"
        )

        await page.wait_for_selector("//div[@class='datepicker-days']")
        # Wait while date picker is loads
        await page.wait_for_selector('//div[@class="loading"]', state="hidden")

        page_text = await page.content()
        soup = BeautifulSoup(page_text, "html.parser")
        cal = Calendar(soup)

        for tag, dt in cal.iter_available_days():
            tag: Tag
            dt: datetime

            # Wait for a needed day
            if dt.day != 2:
                continue

            # Select needed day
            await page.click(f"//td[@data-date='{tag["data-date"]}']")
            # Click on checkbox before finish
            await page.click("//input[@class='form-check-input']")
            # Click on the finish button
            await page.get_by_text(re.compile("Transmite.*")).click()

            # Wait for success message
            await page.get_by_text(re.compile(r"Felicitări!.*")).wait_for(
                timeout=60000
            )
            # Make a screenshot in memory
            screenshot = await page.screenshot(full_page=True)
            # Send to telegram chat
            await send_screenshot_to_chat(screenshot)
            del screenshot
            return


async def main() -> None:
    """Entrypoint."""
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )
        
        async def work(row: Series):
            context = await browser.new_context(record_video_dir="videos/")

            try:
                await make_an_appointment(context, row)
            except Exception as exc:
                logger.exception(exc)

            await context.close()
        
        tasks = []
        for index, row in (await get_df()).iterrows():
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
