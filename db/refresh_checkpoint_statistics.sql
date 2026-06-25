CREATE OR REPLACE FUNCTION public.refresh_checkpoint_statistics()
RETURNS VOID AS $$
BEGIN
    WITH recent_actuals AS (
        -- Priority 0: Actual border crossings by real users
        -- Note: border_crossings doesn't have transport_type, defaulting to 'car'
        SELECT 
            checkpoint_id,
            direction,
            'car'::TEXT AS transport_type,
            (duration_seconds / 60)::INTEGER AS duration_minutes
        FROM public.border_crossings
        WHERE completed_at > NOW() - INTERVAL '6 hours'
    ),
    actual_averages AS (
        SELECT 
            checkpoint_id,
            direction,
            transport_type,
            AVG(duration_minutes)::INTEGER AS avg_time,
            COUNT(*) AS r_count,
            0 AS sorting_priority,
            'ACTUAL'::TEXT AS data_source,
            NULL::BOOLEAN AS is_jammed,
            NULL::BOOLEAN AS is_warning
        FROM recent_actuals
        GROUP BY checkpoint_id, direction, transport_type
    ),
    llm_latest AS (
        -- Priority 1: Latest LLM/API Prediction (is_manual = false)
        SELECT DISTINCT ON (checkpoint_id, direction, transport_type)
            checkpoint_id,
            direction,
            transport_type,
            duration_minutes AS avg_time,
            1 AS r_count,
            1 AS sorting_priority,
            'PREDICTION'::TEXT AS data_source,
            (metadata->'llm'->>'is_jammed')::BOOLEAN AS is_jammed,
            (metadata->'llm'->>'is_warning')::BOOLEAN AS is_warning
        FROM public.time_stat
        WHERE is_manual = false
        ORDER BY checkpoint_id, direction, transport_type, recorded_at DESC
    ),
    admin_fallback_latest AS (
        -- Priority 2: Latest Fallback Math Calculation (is_manual = true)
        SELECT DISTINCT ON (checkpoint_id, direction, transport_type)
            checkpoint_id,
            direction,
            transport_type,
            duration_minutes AS avg_time,
            1 AS r_count,
            2 AS sorting_priority,
            'ADMIN'::TEXT AS data_source,
            (metadata->'llm'->>'is_jammed')::BOOLEAN AS is_jammed,
            (metadata->'llm'->>'is_warning')::BOOLEAN AS is_warning
        FROM public.time_stat
        WHERE is_manual = true
        ORDER BY checkpoint_id, direction, transport_type, recorded_at DESC
    ),
    combined_results AS (
        SELECT * FROM actual_averages
        UNION ALL
        SELECT * FROM llm_latest
        UNION ALL
        SELECT * FROM admin_fallback_latest
    ),
    filtered_results AS (
        -- DISTINCT ON picks the first matching row based on the ORDER BY
        SELECT DISTINCT ON (checkpoint_id, direction, transport_type)
            checkpoint_id,
            direction,
            transport_type,
            avg_time,
            r_count,
            data_source,
            is_jammed,
            is_warning
        FROM combined_results
        ORDER BY checkpoint_id, direction, transport_type, sorting_priority ASC
    )
    -- Upsert the compiled results straight into our dedicated lookup table
    INSERT INTO public.checkpoint_status (checkpoint_id, direction, transport_type, avg_duration_minutes, reports_count, data_source, updated_at, is_warning, is_jammed)
    SELECT checkpoint_id, direction, transport_type, avg_time, r_count, data_source, NOW(), is_warning, is_jammed
    FROM filtered_results
    ON CONFLICT (checkpoint_id, direction, transport_type) 
    DO UPDATE SET 
        avg_duration_minutes = EXCLUDED.avg_duration_minutes,
        reports_count = EXCLUDED.reports_count,
        data_source = EXCLUDED.data_source,
        updated_at = EXCLUDED.updated_at,
        is_warning = COALESCE(EXCLUDED.is_warning, checkpoint_status.is_warning),
        is_jammed = COALESCE(EXCLUDED.is_jammed, checkpoint_status.is_jammed);
END;
$$ LANGUAGE plpgsql;

-- 1. Ensure the extension is enabled
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- 2. Schedule the job
SELECT cron.schedule(
    'refresh-border-stats-job',  -- Unique name for your job
    '*/30 * * * *',              -- Standard Cron syntax (Every 15 minutes)
    $$ SELECT refresh_checkpoint_statistics(); $$
);
