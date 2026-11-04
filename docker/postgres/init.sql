-- Initialize the database
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Create the main database (already created by POSTGRES_DB env var)
-- This script runs on first startup

-- Set timezone
SET timezone = 'Asia/Kolkata';
