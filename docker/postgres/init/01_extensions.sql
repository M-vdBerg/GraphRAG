-- Load required extensions
CREATE EXTENSION IF NOT EXISTS age;
CREATE EXTENSION IF NOT EXISTS vector;

-- Make AGE catalog available in search path
LOAD 'age';
SET search_path = ag_catalog, "$user", public;
