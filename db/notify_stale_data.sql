-- Alerts the admin via Telegram when public.time_stat has not received a
-- fresh record (extracted_at, falling back to recorded_at) in the last 6 hours.
-- Throttled to at most one notification per day via public.alert_notifications
-- (defined in schema.sql).
CREATE OR REPLACE FUNCTION public.notify_if_data_stale()
RETURNS VOID AS $$
DECLARE
    v_bot_token TEXT := '<TELEGRAM_BOT_TOKEN>';       -- TODO: fill in, keep out of git history
    v_admin_chat_id TEXT := '<ADMIN_TELEGRAM_CHAT_ID>'; -- TODO: fill in, keep out of git history
    v_alert_key TEXT := 'stale_time_stat';
    v_last_update TIMESTAMPTZ;
    v_last_notified_at TIMESTAMPTZ;
BEGIN
    SELECT MAX(COALESCE(extracted_at, recorded_at))
    INTO v_last_update
    FROM public.time_stat;

    IF v_last_update IS NOT NULL AND v_last_update >= NOW() - INTERVAL '6 hours' THEN
        RETURN;
    END IF;

    SELECT last_notified_at INTO v_last_notified_at
    FROM public.alert_notifications
    WHERE alert_key = v_alert_key;

    IF v_last_notified_at IS NOT NULL AND v_last_notified_at >= NOW() - INTERVAL '1 day' THEN
        RETURN;
    END IF;

    -- pg_net's net.http_post is async/non-blocking: it enqueues the request
    -- and returns immediately, the actual call runs in a background worker.
    PERFORM net.http_post(
        url := 'https://api.telegram.org/bot' || v_bot_token || '/sendMessage',
        headers := jsonb_build_object('Content-Type', 'application/json'),
        body := jsonb_build_object(
            'chat_id', v_admin_chat_id,
            'text', '⚠️ Supabase Alert: Data has not updated in the last 6 hours!'
        )
    );

    INSERT INTO public.alert_notifications (alert_key, last_notified_at)
    VALUES (v_alert_key, NOW())
    ON CONFLICT (alert_key) DO UPDATE SET last_notified_at = EXCLUDED.last_notified_at;
END;
$$ LANGUAGE plpgsql;

-- 1. Ensure the async HTTP extension is enabled (bundled with Supabase, exposed via the `net` schema)
CREATE EXTENSION IF NOT EXISTS pg_net;

-- 2. Schedule the job to run once every 2 hours
SELECT cron.schedule(
    'notify-stale-data-job',   -- Unique name for your job
    '0 */2 * * *',             -- Standard Cron syntax (every 2 hours)
    $$ SELECT public.notify_if_data_stale(); $$
);
