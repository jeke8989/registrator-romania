import asyncio
import json

import gspread_asyncio
from config import get_config
from google.oauth2.service_account import Credentials
from loguru import logger
from pandas import DataFrame


def get_creds() -> Credentials:
    """Get google spreadsheet credentails."""
    cfg = get_config()
    creds = Credentials.from_service_account_file(cfg["GOOGLE_TOKEN_FILE"])
    return creds.with_scopes(
        [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
    )


async def get_df() -> DataFrame:
    """Get DataFrame of users (very good api for work with .csv)."""
    manager = gspread_asyncio.AsyncioGspreadClientManager(get_creds)
    logger.info("try to authorizate in gsheets")
    agc = await manager.authorize()
    logger.info("try to open by url")
    sheet = await agc.open_by_url(
        "https://docs.google.com/spreadsheets/d/1ZdSqEGjV1L3Chj2a7eFc7YDcqoU16-A-RwTrpaVBfNs/edit#gid=0"
    )
    logger.info("try to get sheet")
    sheet1 = await sheet.get_sheet1()
    logger.info("try to get records")
    table_data = await sheet1.get_all_records()
    # with open("spr.json") as f:
    #     table_data = json.load(f)
    return DataFrame(table_data)


async def main() -> None:
    """Entrypoint."""
    df = await get_df()
    for i, row in df.iterrows():
        print(row)

    print(len(df))


if __name__ == "__main__":
    asyncio.run(main())
