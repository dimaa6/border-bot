## BorderBot: Serverless Border Crossing Monitor

A lightweight, production-ready Telegram bot built to track and crowdsource border crossing wait times using a highly responsive backend.

[Run bot in Telegram](https://t.me/ua_border_traffic_bot)

## High-Level Architecture & Tech Stack

**Infrastructure:** Telegram Webhook.

**Compute:** Python Flask server.

**Database:** Supabase (PostgreSQL) for lightweight, high-speed connection pooling.

**UX Highlight:**
- Non-blocking UI flow. Users are reminded to update their status
- instant session teardown with asynchronous inline timestamp adjustments.

## Key Features

1. 🚀 Instant Telemetry: Real-time crowd-sourced data via structured Telegram inputs.

2. ⏳ Smart Stale-Session Management: Automated cron based tracking and cleaning up abandoned crossings.

3. 📉 Frictionless UX: Asynchronous feedback loops letting users update their crossing times without locking up the core state machine.

## Configuration & Environment Variables

1. TELEGRAM_SECRET_TOKEN - the token Telegram will send to WebHook to authenticate itself
2. TELEGRAM_BOT_TOKEN - our bot token
3. SUPABASE_URL - Supabase URL of our database
4. SUPABASE_SERVICE_KEY - Supabase secret key
5. ADMIN_USER_ID - Telegram admin user id
6. REDIS_HOST - Redis host
7. REDIS_PORT - Redis port

## Quick Start / Deployment Guide

1. Rename .env.example to .env and fill in the values
2. To run standalone:
   1. Copy env.example to .env and provide the values
   1. If redis is listening on localhost, provide REDIS_HOST=localhost in .env
   1. Provide option LOG_DIR=./logs and mkdir logs if this dir does not exist
   1. Run docker compose -f docker-compose-debug.yaml up
   1. You can access redis insight at http://localhost:5540
3. To run in production:
    1. Copy .env.compose.example to .env.compose and edit it
    1. mkdir logs
    1. Run docker compose --env-file .env.compose build
    1. Run docker compose up -d if you don't need redis insight
    1. Run docker compose --profile debug up -d if you need redis insight at http://localhost:5540. If you are running on headless Linux box, create a SSH tunnel between your local machine and the server's port 5540: ssh -L 5540:localhost:5540 user@your-server
