# syntax=docker/dockerfile:1
FROM python:3.13-slim AS builder

WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir .
COPY . .
RUN pip install --no-cache-dir .

FROM python:3.13-slim
WORKDIR /app
COPY --from=builder /app /app
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

EXPOSE 8000
CMD ["uvicorn", "bot.web:app", "--host", "0.0.0.0", "--port", "8000"]
