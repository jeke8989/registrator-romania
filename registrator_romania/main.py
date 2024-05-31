import asyncio
import os
import subprocess
from datetime import datetime, timedelta

from registrator_romania.scheduler import start_scheduler


async def keep_running() -> None:
    """Kepp asyncio.event_loop."""
    while True:
        await asyncio.sleep(3600)


async def main() -> None:
    """Entrypoint."""
    process = None
    
    if "DISPLAY" not in os.environ:
        os.environ["DISPLAY"] = ":99"
        process = subprocess.Popen(
            ["Xvfb", ":99", "-screen", "0", "1024x768x16"]
        )

    dt = datetime.now() + timedelta(seconds=5)
    await start_scheduler(start_date=dt)
    await keep_running()
    
    if process:
        process.kill()



if __name__ == "__main__":
    asyncio.run(main())
