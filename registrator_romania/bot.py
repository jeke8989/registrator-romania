"""Module contain functional for work with Telegram Bot."""


from aiogram import Bot, Dispatcher
from aiogram.types import BufferedInputFile

from registrator_romania.config import get_config

cfg = get_config()
bot = Bot(cfg["BOT_TOKEN"])
dp = Dispatcher()


async def send_screenshot_to_chat(screenshot: bytes) -> None:
    """Send screenshot to Telegram chat."""
    await bot.send_photo(
        get_config()["telegram_bot"]["chat_id"],
        BufferedInputFile(screenshot, "screenshot.png"),
    )
    await bot.session.close()
    del screenshot
