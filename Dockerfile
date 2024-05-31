FROM python:3.12

RUN pip install poetry

WORKDIR /app

COPY pyproject.toml /app/
RUN poetry config virtualenvs.create false
RUN poetry install --no-root --no-interaction --no-ansi

COPY . /app

RUN apt update -y
RUN apt install xvfb -y
RUN playwright install-deps
RUN playwright install chromium

ENTRYPOINT [ "python", "registrator_romania/main.py" ]