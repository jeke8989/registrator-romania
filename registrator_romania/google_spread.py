import asyncio
import json
import os

import gspread_asyncio
from google.oauth2.service_account import Credentials
from loguru import logger
from pandas import DataFrame

from registrator_romania.config import get_config


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


async def get_df(from_json: bool = False) -> DataFrame:
    """Get DataFrame of users (very good api for work with .csv)."""
    manager = gspread_asyncio.AsyncioGspreadClientManager(get_creds)
    if from_json and not os.path.exists("spr.json"):
        from_json = False

    if not from_json:
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
        table_data = [{k: v.strip() for k, v in d.items()} for d in table_data]
        with open("spr.json", "w") as f:
            json.dump(table_data, f, indent=2, ensure_ascii=False)
    else:
        with open("spr.json") as f:
            table_data = json.load(f)
        logger.info("get users data from json file")

    return DataFrame(table_data)


async def main() -> None:
    """Entrypoint."""
    df = await get_df()
    for i, row in df.iterrows():
        print(row)

    print(len(df))


if __name__ == "__main__":
    asyncio.run(main())
