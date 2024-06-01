from datetime import datetime
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from registrator_romania.browser import main


async def start_scheduler(**kwargs) -> None:
    """Run scheduler that trigger work with browser."""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(main, "cron", max_instances=1, **kwargs)
    scheduler.start()
    dt = datetime.now()
    logger.info(f"Start scheduler. Date is {dt}")
    logging.getLogger("apscheduler").setLevel(logging.INFO)
