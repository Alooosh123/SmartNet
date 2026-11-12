FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app/backend

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./

RUN mkdir -p uploads/cards uploads/receipts static/pdfs \
    && useradd --create-home --shell /usr/sbin/nologin smartnet \
    && chown -R smartnet:smartnet /app/backend

USER smartnet

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app:app --host 0.0.0.0 --port 8000"]
