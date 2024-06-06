import asyncio
from datetime import datetime, timedelta

from zoneinfo import ZoneInfo

from registrator_romania.scheduler import start_scheduler


async def keep_running() -> None:
    """Kepp asyncio.event_loop."""
    while True:
        await asyncio.sleep(3600)


async def main() -> None:
    """Entrypoint."""
    dt = datetime.now() + timedelta(seconds=10)
    await start_scheduler(
        hour=8, minute=59, seconds=30, timezone=ZoneInfo("Europe/Moscow")
    )
    await keep_running()


if __name__ == "__main__":
    asyncio.run(main())
