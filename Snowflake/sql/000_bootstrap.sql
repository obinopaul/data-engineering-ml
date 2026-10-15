-- Run this whole file in a Snowsight SQL worksheet as your existing admin user,
-- or use: python Snowflake/connection.py --setup
-- Reuses COMPUTE_WH. Creates no warehouse, password, or additional user.
-- Pattern: main/snowflake_rbac_lab.sql, adapted to the ingestion/dbt workspace.

USE ROLE SYSADMIN;
CREATE DATABASE IF NOT EXISTS INTERVIEW_DB;
CREATE SCHEMA IF NOT EXISTS INTERVIEW_DB.RAW;
CREATE SCHEMA IF NOT EXISTS INTERVIEW_DB.STAGING;
CREATE SCHEMA IF NOT EXISTS INTERVIEW_DB.ANALYTICS;

USE ROLE SECURITYADMIN;
CREATE ROLE IF NOT EXISTS INTERVIEW_ROLE
    COMMENT = 'Ingestion and dbt access to the interview database';
GRANT ROLE INTERVIEW_ROLE TO ROLE SYSADMIN;

GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE INTERVIEW_ROLE;
GRANT USAGE, CREATE SCHEMA ON DATABASE INTERVIEW_DB TO ROLE INTERVIEW_ROLE;
GRANT USAGE, CREATE TABLE, CREATE VIEW
    ON SCHEMA INTERVIEW_DB.RAW TO ROLE INTERVIEW_ROLE;
GRANT USAGE, CREATE TABLE, CREATE VIEW
    ON SCHEMA INTERVIEW_DB.STAGING TO ROLE INTERVIEW_ROLE;
GRANT USAGE, CREATE TABLE, CREATE VIEW
    ON SCHEMA INTERVIEW_DB.ANALYTICS TO ROLE INTERVIEW_ROLE;

-- Quote the current user's exact identifier, including mixed case if present.
SET interview_user_identifier = (SELECT '"' || REPLACE(CURRENT_USER(), '"', '""') || '"');
GRANT ROLE INTERVIEW_ROLE TO USER IDENTIFIER($interview_user_identifier);

-- Verify using only the intended working role, without inherited secondary roles.
USE ROLE INTERVIEW_ROLE;
USE SECONDARY ROLES NONE;
USE WAREHOUSE COMPUTE_WH;
USE DATABASE INTERVIEW_DB;
USE SCHEMA ANALYTICS;

-- dlt merge loads need a staging schema; exercise the CREATE SCHEMA grant.
CREATE SCHEMA IF NOT EXISTS INTERVIEW_DB.RAW_STAGING;
-- Temporary tables disappear when this session ends; no business table is replaced.
-- Evaluate generated values in a scalar query: direct SET expressions reject
-- non-constant functions such as UUID_STRING(). Keep names unique on every run.
SET raw_check = (SELECT 'INTERVIEW_DB.RAW._SETUP_' || REPLACE(UUID_STRING(), '-', '_'));
SET analytics_check = (SELECT 'INTERVIEW_DB.ANALYTICS._SETUP_' || REPLACE(UUID_STRING(), '-', '_'));
CREATE TEMPORARY TABLE IDENTIFIER($raw_check) (id INTEGER);
CREATE TEMPORARY TABLE IDENTIFIER($analytics_check) (id INTEGER);
INSERT INTO IDENTIFIER($raw_check) VALUES (1);
INSERT INTO IDENTIFIER($analytics_check)
    SELECT id FROM IDENTIFIER($raw_check);
SELECT CURRENT_ROLE() AS ACTIVE_ROLE,
       (SELECT COUNT(*) FROM IDENTIFIER($raw_check)) AS RAW_ROWS,
       (SELECT COUNT(*) FROM IDENTIFIER($analytics_check)) AS ANALYTICS_ROWS;
