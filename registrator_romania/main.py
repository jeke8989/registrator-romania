import asyncio

import aiofiles
from loguru import logger
from zoneinfo import ZoneInfo

from registrator_romania.scheduler import start_scheduler


async def keep_running() -> None:
    """Kepp asyncio.event_loop."""
    while True:
        await asyncio.sleep(3600)


async def write_log(msg):
    async with aiofiles.open("logs.log", "a") as f:
        await f.write(msg)


async def main() -> None:
    """Entrypoint."""
    # logger.add("log_{time}.log", rotation="1 day", level="INFO", enqueue=True)
    logger.add(write_log, level="INFO", enqueue=True)

    await start_scheduler(
        hour=8,
        minute=29,
        second=0,
        timezone=ZoneInfo("Europe/Moscow"),
    )

    await keep_running()


if __name__ == "__main__":
    asyncio.run(main())
