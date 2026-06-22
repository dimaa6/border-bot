FROM python:3.12-alpine

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

ARG USER_ID=1000
ARG GROUP_ID=1000
ARG PORT=8000
ENV PORT=${PORT}

RUN addgroup -g ${GROUP_ID} appgroup && adduser -D -u ${USER_ID} -G appgroup appuser

RUN mkdir -p /app/logs && chown -R appuser:appgroup /app/logs

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appgroup . .

USER appuser

CMD uvicorn main:app --app-dir ./src --host 0.0.0.0 --port $PORT
