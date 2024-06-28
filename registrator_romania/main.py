import asyncio
from datetime import datetime, timedelta

from loguru import logger
from zoneinfo import ZoneInfo

from registrator_romania.bot import send_msg_into_chat
from registrator_romania.proxy import check_proxy, get_proxies
from registrator_romania.scheduler import start_scheduler


async def keep_running() -> None:
    """Kepp asyncio.event_loop."""
    while True:
        await asyncio.sleep(3600)


async def main() -> None:
    """Entrypoint."""
    # logger.add(send_msg_into_chat, level="INFO")
    logger.add("log_{time}.log", rotation="1 day", level="INFO")
    await start_scheduler(
        hour=8,
        minute=59,
        second=30,
        timezone=ZoneInfo("Europe/Moscow"),
    )

    await keep_running()


if __name__ == "__main__":
    asyncio.run(main())
