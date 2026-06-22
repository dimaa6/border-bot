-- Create table for completed crossings (The Analytics Database)
CREATE TABLE public.border_crossings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id BIGINT,          -- Kept so you can analyze regular travelers if needed
    checkpoint_id TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('INBOUND', 'OUTBOUND')),
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    duration_seconds INTEGER NOT NULL -- Pre-calculated during the "I'm through" click
);

-- Create high-performance indexes for future time-series analytics
CREATE INDEX idx_crossings_analytics 
ON public.border_crossings (checkpoint_id, direction, completed_at);

-- Create an index to quickly check for recent user crossings (Rate-limiting in handler.py)
CREATE INDEX idx_border_crossings_chat_completed
ON public.border_crossings (chat_id, completed_at);

-- Create table for time statistics (time_stat)
CREATE TABLE public.time_stat (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    checkpoint_id VARCHAR(50) NOT NULL,
    direction VARCHAR(20) NOT NULL CHECK (direction IN ('INBOUND', 'OUTBOUND')),
    transport_type VARCHAR(20) NOT NULL DEFAULT 'car' CHECK (transport_type IN ('car', 'bus', 'truck', 'van')),
    cars_queue_size  INTEGER,
    duration_minutes INTEGER,
    comment TEXT,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_manual BOOLEAN NOT NULL DEFAULT FALSE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- create tale for scraper configuration
CREATE TABLE checkpoint_scraper_config (
    checkpoint_id TEXT PRIMARY KEY,                       -- Your exact bot codes (e.g., 'PL_SHEHYNI', 'PL_USTYLUH')
    display_name TEXT NOT NULL,                           -- Friendly Ukrainian name for prompts (e.g., 'Шегині', 'Устилуг')
    telegram_handle TEXT NOT NULL,                        -- Public group username (e.g., 'ustilug_zosin_chat')
    telegram_chat_id BIGINT,                              -- 64-bit Telegram ID (handles negative values safely)
    lookback_hours INT NOT NULL DEFAULT 3,                -- Configurable context window per checkpoint
    active BOOLEAN NOT NULL DEFAULT TRUE,                 -- Kill-switch to pause scraping
    last_message_id INT NOT NULL DEFAULT 0,               -- High-water mark for Telethon's min_id
    last_scraped_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    config_matrix JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- Indexing for execution loops
CREATE INDEX IF NOT EXISTS idx_active_checkpoints ON checkpoint_scraper_config (active);
