DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'offboard_app') THEN
    CREATE ROLE offboard_app LOGIN PASSWORD 'offboard_app';
  END IF;
END
$$;
