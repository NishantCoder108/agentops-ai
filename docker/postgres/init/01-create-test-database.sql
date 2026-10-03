-- Runs once, when the data volume is first initialised.
-- A separate database for pytest, so tests never touch development data.
CREATE DATABASE agentops_test;
