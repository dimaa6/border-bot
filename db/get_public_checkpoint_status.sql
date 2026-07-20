CREATE OR REPLACE FUNCTION get_public_checkpoint_status(
    p_country_code TEXT,
    p_direction TEXT
)
RETURNS SETOF public.checkpoint_status
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    RETURN QUERY
    SELECT * 
    FROM public.checkpoint_status
    WHERE checkpoint_id LIKE p_country_code || '_%'
      AND direction = p_direction;
END;
$$;