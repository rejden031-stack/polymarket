FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY config/ ./config/
COPY bot/ ./bot/

ENV CONFIG_PATH=config/config.yaml \
    PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "bot.web:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
