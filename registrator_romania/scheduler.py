import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from registrator_romania.browser import main


async def start_scheduler(**kwargs) -> None:
    """Run scheduler that trigger work with browser."""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(main, "cron", max_instances=1, **kwargs)
    scheduler.start()
    logging.getLogger("apscheduler").setLevel(logging.ERROR)
