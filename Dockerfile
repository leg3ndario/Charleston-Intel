FROM python:3.12-slim

# Playwright deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates fonts-liberation libnss3 libatk-bridge2.0-0 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libasound2 libatspi2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m playwright install chromium

COPY . .

ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app

# Default: run the API. Override with `docker run ... python -m scheduler.runner` for the worker.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
