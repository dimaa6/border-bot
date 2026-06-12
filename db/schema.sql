-- 1. Create table for tracking active crossings (The State Machine)
CREATE TABLE public.active_sessions (
    chat_id BIGINT PRIMARY KEY,
    checkpoint_id TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('INBOUND', 'OUTBOUND')), -- 'INBOUND' (Entering UA) or 'OUTBOUND' (Leaving UA)
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_reminded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_user_action_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Create table for completed crossings (The Analytics Database)
CREATE TABLE public.border_crossings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id BIGINT,          -- Kept so you can analyze regular travelers if needed
    checkpoint_id TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('INBOUND', 'OUTBOUND')),
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    duration_seconds INTEGER NOT NULL -- Pre-calculated during the "I'm through" click
);

-- 3. Create high-performance indexes for future time-series analytics
CREATE INDEX idx_crossings_analytics 
ON public.border_crossings (checkpoint_id, direction, completed_at);

CREATE INDEX idx_active_sessions_last_reminded_at 
ON public.active_sessions (last_reminded_at);

CREATE INDEX idx_active_sessions_last_useract_at 
ON public.active_sessions (last_user_action_at);

-- 4. Create an index to quickly check for recent user crossings (Rate-limiting in handler.py)
CREATE INDEX idx_border_crossings_chat_completed
ON public.border_crossings (chat_id, completed_at);
