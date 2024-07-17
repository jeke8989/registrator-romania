from datetime import datetime
from pprint import pprint
import re
from docx import Document
import pandas as pd

from registrator_romania.new_request_registrator import prepare_users_data


class Transliterator:
    def __init__(self, language):
        if language == "tr":
            self.translit_dict = {
                "Ş": "S",
                "ş": "s",
                "İ": "I",
                "ı": "i",
                "Ğ": "G",
                "ğ": "g",
                "Ç": "C",
                "ç": "c",
                "Ö": "O",
                "ö": "o",
                "Ü": "U",
                "ü": "u",
            }
        else:
            self.translit_dict = {}

    def transliterate(self, text):
        return "".join(self.translit_dict.get(char, char) for char in text)


def get_users_data_from_docx():
    doc = Document("users.docx")
    user = False
    template = {
        "Nume Pasaport": "",
        "Prenume Pasaport": "",
        "Data nasterii": "",
        "Locul naşterii": "",
        "Prenume Mama": "",
        "Prenume Tata": "",
        "Adresa de email": "",
        "Serie și număr Pașaport": "",
    }
    users = []
    user = {}
    mapping = {
        "Prenume Pasaport": ["Prenume"],
        "Nume Pasaport": ["Nume"],
        "Data nasterii": ["Data naşterii"],
        "Locul naşterii": ["Locul naşterii"],
        "Prenume Mama": ["Prenumele mamei", "Numele mame", "Numele mamei"],
        "Prenume Tata": [
            "Prenumele tatalui",
            "Numele tatalui",
        ],
        "Adresa de email": ["Adresa de e-mail"],
        "Serie și număr Pașaport": ["Seria şi numar Paşaport"],
    }
    for paragraph in doc.paragraphs:
        text = paragraph.text.replace("\n", "").strip()
        if not text:
            continue

        record = re.findall(r"(^[\d\.]*)(.*)", text)[0][1]
        col, val = list(map(lambda v: v.strip(), record.split(":")))

        key = None
        for k, v in mapping.items():
            if col in v:
                key = k
                break

        assert key
        val = Transliterator("tr").transliterate(val)

        if key == "Data nasterii":
            try:
                dt = datetime.strptime(val, "%Y-%m-%d")
            except Exception:
                dt = datetime.strptime(val, "%d-%m-%Y")
            val = dt.strftime("%Y-%m-%d")
        elif key == "":
            val = val.lower()

        user[key] = val

        if key == "Serie și număr Pașaport":
            users.append(user.copy())
            user.clear()

    return prepare_users_data(users)


def get_users_data_from_csv():
    df = pd.read_csv("users.csv")
    users_data = df.to_dict("records")
    return prepare_users_data(users_data)
