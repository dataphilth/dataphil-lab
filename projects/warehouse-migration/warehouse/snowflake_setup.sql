-- snowflake_setup.sql
-- Run once in a Snowsight worksheet, signed in as your trial admin user.
-- Creates: a cost-capped warehouse, a role, a key-pair service user,
-- the MLB database (RAW + ANALYTICS schemas), a Parquet stage, and RAW tables.
--
-- BEFORE RUNNING: paste your public key (contents of rsa_key.pub, without the
-- BEGIN/END lines, all on one line) into the RSA_PUBLIC_KEY value below.

USE ROLE ACCOUNTADMIN;

-- ---------------------------------------------------------------- compute
-- XSMALL + 60s auto-suspend keeps the trial credits from bleeding out.
CREATE WAREHOUSE IF NOT EXISTS MIGRATION_WH
  WAREHOUSE_SIZE = 'XSMALL'
  AUTO_SUSPEND = 60
  AUTO_RESUME = TRUE
  INITIALLY_SUSPENDED = TRUE;

-- Hard stop: suspend the warehouse if it burns 20 credits in a month.
CREATE RESOURCE MONITOR IF NOT EXISTS MIGRATION_MONITOR
  WITH CREDIT_QUOTA = 20
  TRIGGERS ON 80 PERCENT DO NOTIFY
           ON 100 PERCENT DO SUSPEND;
ALTER WAREHOUSE MIGRATION_WH SET RESOURCE_MONITOR = MIGRATION_MONITOR;

-- ---------------------------------------------------------------- storage
CREATE DATABASE IF NOT EXISTS MLB;
CREATE SCHEMA IF NOT EXISTS MLB.RAW;        -- landed exactly as extracted
CREATE SCHEMA IF NOT EXISTS MLB.ANALYTICS;  -- dbt builds the star schema here

-- ---------------------------------------------------------------- access
CREATE ROLE IF NOT EXISTS MIGRATION_ROLE;
GRANT ROLE MIGRATION_ROLE TO ROLE SYSADMIN;
GRANT USAGE, OPERATE ON WAREHOUSE MIGRATION_WH TO ROLE MIGRATION_ROLE;
GRANT ALL ON DATABASE MLB TO ROLE MIGRATION_ROLE;
GRANT ALL ON SCHEMA MLB.RAW TO ROLE MIGRATION_ROLE;
GRANT ALL ON SCHEMA MLB.ANALYTICS TO ROLE MIGRATION_ROLE;

-- Service user for scripts + dbt. TYPE = SERVICE means no password at all:
-- it authenticates with the key pair only.
CREATE USER IF NOT EXISTS MIGRATION_SVC
  TYPE = SERVICE
  DEFAULT_ROLE = MIGRATION_ROLE
  DEFAULT_WAREHOUSE = MIGRATION_WH
  RSA_PUBLIC_KEY = 'PASTE_PUBLIC_KEY_HERE';
GRANT ROLE MIGRATION_ROLE TO USER MIGRATION_SVC;

-- ---------------------------------------------------------------- RAW layer
-- From here on, objects are owned by the migration role.
USE ROLE MIGRATION_ROLE;
USE WAREHOUSE MIGRATION_WH;
USE SCHEMA MLB.RAW;

CREATE STAGE IF NOT EXISTS MLB_PARQUET_STAGE
  FILE_FORMAT = (TYPE = PARQUET);

-- Type translation from SQLite:
--   INTEGER -> NUMBER(38,0)   REAL -> FLOAT   TEXT -> VARCHAR
-- Dates stay VARCHAR here on purpose (SQLite stores them as text). RAW keeps
-- the source shape; staging models in dbt cast them. That is ELT.
-- Note: Snowflake accepts PRIMARY KEY / FOREIGN KEY / CHECK syntax but only
-- enforces NOT NULL. Uniqueness and relationships are checked by dbt tests.

CREATE OR REPLACE TABLE players (
  mlbam_id          NUMBER(38,0) NOT NULL,
  full_name         VARCHAR NOT NULL,
  primary_position  VARCHAR,
  bats              VARCHAR,
  throws            VARCHAR,
  debut_date        VARCHAR,
  birth_date        VARCHAR,
  last_updated      VARCHAR
);

CREATE OR REPLACE TABLE teams (
  team_id           NUMBER(38,0) NOT NULL,
  abbr              VARCHAR NOT NULL,
  full_name         VARCHAR NOT NULL,
  league            VARCHAR,
  division          VARCHAR,
  current_park_id   NUMBER(38,0),
  last_updated      VARCHAR
);

CREATE OR REPLACE TABLE parks (
  park_id           NUMBER(38,0) NOT NULL,
  name              VARCHAR NOT NULL,
  city              VARCHAR,
  state             VARCHAR,
  lat               FLOAT,
  lon               FLOAT,
  altitude_ft       NUMBER(38,0),
  surface           VARCHAR,
  roof              VARCHAR,
  lf_dist_ft        NUMBER(38,0),
  cf_dist_ft        NUMBER(38,0),
  rf_dist_ft        NUMBER(38,0),
  run_factor        FLOAT,
  hr_factor_lhb     FLOAT,
  hr_factor_rhb     FLOAT,
  last_updated      VARCHAR
);

CREATE OR REPLACE TABLE seasons (
  season            NUMBER(38,0) NOT NULL,
  start_date        VARCHAR,
  end_date          VARCHAR,
  shift_ban         NUMBER(38,0),
  universal_dh      NUMBER(38,0),
  pitch_clock       NUMBER(38,0),
  bigger_bases      NUMBER(38,0),
  ball_era_label    VARCHAR,
  notes             VARCHAR
);

CREATE OR REPLACE TABLE games (
  game_pk           NUMBER(38,0) NOT NULL,
  game_date         VARCHAR NOT NULL,
  season            NUMBER(38,0) NOT NULL,
  home_team         VARCHAR NOT NULL,
  away_team         VARCHAR NOT NULL,
  park_id           NUMBER(38,0),
  home_pitcher_id   NUMBER(38,0),
  away_pitcher_id   NUMBER(38,0),
  ump_id            NUMBER(38,0),
  weather_temp_f    FLOAT,
  weather_wind_mph  FLOAT,
  weather_wind_dir  VARCHAR,
  weather_humidity  FLOAT,
  game_status       VARCHAR,
  first_pitch_ts    VARCHAR,
  last_updated      VARCHAR
);

-- total_runs was a GENERATED column in SQLite; not migrated, rebuilt in dbt.
CREATE OR REPLACE TABLE game_results (
  game_pk           NUMBER(38,0) NOT NULL,
  home_runs         NUMBER(38,0) NOT NULL,
  away_runs         NUMBER(38,0) NOT NULL,
  home_hits         NUMBER(38,0),
  away_hits         NUMBER(38,0),
  home_errors       NUMBER(38,0),
  away_errors       NUMBER(38,0),
  innings_played    FLOAT,
  decided_at        VARCHAR
);

-- hrr was a GENERATED column in SQLite; not migrated, rebuilt in dbt.
CREATE OR REPLACE TABLE batter_game_stats (
  game_pk             NUMBER(38,0) NOT NULL,
  batter_id           NUMBER(38,0) NOT NULL,
  game_date           VARCHAR NOT NULL,
  team_id             NUMBER(38,0),
  batting_order_slot  NUMBER(38,0),
  plate_appearances   NUMBER(38,0) NOT NULL,
  at_bats             NUMBER(38,0) NOT NULL,
  hits                NUMBER(38,0) NOT NULL,
  runs                NUMBER(38,0) NOT NULL,
  rbis                NUMBER(38,0) NOT NULL,
  source              VARCHAR,
  ingested_at_utc     VARCHAR
);
