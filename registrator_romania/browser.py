from __future__ import annotations

import asyncio
import os
import random
import re
import subprocess
from datetime import datetime
import time
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
        first_name = ''.join(random.sample(first_name, len(first_name)))
        last_name = ''.join(random.sample(last_name, len(last_name)))
        date_of_birthday = ''.join(random.sample(date_of_birthday, len(date_of_birthday)))
        birthday_place = ''.join(random.sample(birthday_place, len(birthday_place)))
        mother_name = ''.join(random.sample(mother_name, len(mother_name)))
        father_name = ''.join(random.sample(father_name, len(father_name)))
        email = ''.join(random.sample(email, len(email)))
        series_passport = ''.join(random.sample(series_passport, len(series_passport)))

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
    em = row["Adresa de email"]
    logger.info(f"start work of row = {em}. open page...")
    page = await context.new_page()
    await page.goto(URL)
    
    logger.info(f"select needed articolul...\n {em}")
    # Open dropdown with a list of articoluls.
    xpath_dropdown = "//span[@id='select2-tip_formular-container']"
    await page.click(xpath_dropdown)

    # Select needed artcolul
    num = 11
    xpath_articolul = (
        "//ul[@id='select2-tip_formular-results']//"
        f"li[contains(text(), 'ART. {num}') or contains(text(), 'ART {num}')]"
    )
    await page.click(xpath_articolul)
    
    logger.info(f"fill inputs... {em}")
    await fill_inputs(page, row, test=True)
    logger.info(f"filling inputs successfully {em}")

    switch_month_btn_xpath = (
        "//div[@class='datepicker-days']//th[@class='datepicker-switch']"
    )
    months = await get_available_months(switch_month_btn_xpath, page)
    logger.info(f"available month on articolul {num} - {months}")
    for month in months:
        # Find needed month
        # if month.text != "Oct":
        #     continue
        
        logger.info(f"change month... row - {em}")
        await page.click(switch_month_btn_xpath)
        await page.click(
            f"//span[contains(@class, 'month') and text()='{month.text}']"
        )

        await page.wait_for_selector("//div[@class='datepicker-days']")
        # Wait while date picker is loads
        await page.wait_for_selector('//div[@class="loading"]', state="hidden")

        page_text = await page.content()
        logger.info(f"changing month successfully for {em}.\nHTML\n\n{page_text}")
        soup = BeautifulSoup(page_text, "html.parser")
        cal = Calendar(soup)
        
        for tag, dt in cal.iter_available_days():
            tag: Tag
            dt: datetime

            # Wait for a needed day
            # if dt.day != 2:
            #     continue
            
            # Select needed day
            await page.click(f"//td[@data-date='{tag["data-date"]}']")
            # Click on checkbox before finish
            await page.click("//input[@class='form-check-input']")
            # Click on the finish button
            await page.get_by_text(re.compile("Transmite.*")).click()
            await asyncio.sleep(4)
            html = await page.content()
            logger.info(f"Press finish button. HTML:\n---\n{html}")

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
                if datetime.now() < datetime(2024, 1, 6, hour=9, minute=10):
                    path = f"screenshots/{time.time()}-err.png"
                    await context.pages[0].screenshot(path=path, full_page=True)
                    logger.debug(f"Saved screenshot at path = {path}, after error.")
                    
                    await context.close()
                    return await work(row)

            await context.close()
        
        tasks = []
        df = await get_df()
        for index, row in df.iterrows():
            if len(tasks) <= 10:
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
