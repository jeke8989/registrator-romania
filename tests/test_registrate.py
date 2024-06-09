import random
import string
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
import registrator_romania.request_registration
from pandas import DataFrame


class AsyncMock(MagicMock):
    _free_attempts = 0

    def __await__(self):
        return self._().__await__()

    async def _(self):
        return self

    async def get_free_places_count_on_date(self, *args, **kwargs):
        if self._free_attempts:
            self._free_attempts = 0
            return 5
        self._free_attempts += 1
        return None


def random_str(n: int = 15):
    return "".join(random.choices(string.ascii_uppercase, k=n))


@pytest.mark.asyncio()
async def test_main():
    fake_data = [
        {
            "tip_formular": 3,
            "Nume Pasaport": f"Danii{random_str(2)}",
            "Data Nasterii": date(year=2000, month=5, day=2).strftime(
                "%Y-%m-%d"
            ),
            "Prenume Pasaport": f"Iog{random_str(3)}",
            "Locul Nasterii": random_str(4),
            "Prenume Mama": f"Irin{random_str(1)}",
            "Prenume Tata": f"Ste{random_str(3)}",
            "email": f"{random_str(7)}@gmail.com",
            "Serie și număr Pașaport": random_str(10),
        }
        for _ in range(5)
    ]
    fake_data = DataFrame(fake_data)

    with patch(
        "registrator_romania.request_registration.RequestsRegistrator"
    ) as req_mock, patch(
        "registrator_romania.request_registration.get_df"
    ) as get_df_mock:
        get_df_mock.return_value = fake_data
        req_mock.return_value = AsyncMock()
        await registrator_romania.request_registration.main()
