FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .

RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install -r requirements.txt

COPY . .

RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]
