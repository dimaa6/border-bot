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
   docker compose -f docker-compose-debug.yaml up
3. To run in production:
   Clone https://github.com/dimaa6/border-bot-docker with submodules and follow instructions there.
