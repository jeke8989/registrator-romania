import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from registrator_romania.new_request_registrator import main


async def start_scheduler(**kwargs) -> None:
    """Run scheduler that trigger work with browser."""
    scheduler = AsyncIOScheduler()
    # await main()
    scheduler.add_job(main, "cron", max_instances=1, **kwargs)
    scheduler.start()
    dt = datetime.now()
    logger.info(f"Started scheduler. Datetime is {dt}")
    logging.getLogger("apscheduler").setLevel(logging.INFO)
