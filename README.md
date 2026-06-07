## BorderBot: Serverless Border Crossing Monitor

A lightweight, production-ready Telegram bot built to track and crowdsource border crossing wait times using a highly responsive, serverless backend.

## High-Level Architecture & Tech Stack

**Infrastructure:** AWS SAM (Serverless Application Model) & CloudFormation.

**Compute:** AWS Lambda (Python) splitting duties between API Gateway webhooks for instant user interaction and CloudWatch Events (EventBridge) for automated cron-based housekeeping.

**Database:** Supabase (PostgreSQL) for lightweight, high-speed connection pooling.

**UX Highlight:**
- Non-blocking UI flow. Users are reminded to update their status
- instant session teardown with asynchronous inline timestamp adjustments.

## Key Features

1. 🚀 Instant Telemetry: Real-time crowd-sourced data via structured Telegram inputs.

2. ⏳ Smart Stale-Session Management: Automated Lambda crons tracking and cleaning up abandoned crossings.

3. 📉 Frictionless UX: Asynchronous feedback loops letting users back-date their crossing times without locking up the core state machine.

## Configuration & Environment Variables

1. TelegramSecretToken - the token Telegram will send to WebHook to authenticate itself
2. TelegramBotToken - our bot token
3. SupabaseUrl - Supabase URL of our database
4. SupabaseServiceKey - Supabase secret key

## Quick Start / Deployment Guide

Supply samconfig.toml:

```toml
version = 0.1

[default.deploy.parameters]
stack_name = "your-stack-name"
resolve_s3 = true
s3_prefix = "your-s3-prefix" # may match stack_name
region = "aws_region" # like eu-central-1
confirm_changeset = false
capabilities = "CAPABILITY_IAM"
image_repositories = []
parameter_overrides = [
    "TelegramSecretToken=...",
    "TelegramBotToken=...",
    "SupabaseUrl=...",
    "SupabaseServiceKey=..."
]

[default.global.parameters]
region = "aws_region" # like eu-central-1
```
