#!/bin/bash
# Runs after 01-init.sql (alphabetical order in /docker-entrypoint-initdb.d/).
# Creates the authenticator role with the password from AUTHENTICATOR_PASSWORD env.
# Kept as a shell script because .sql files in initdb can't substitute env vars.
set -e

: "${AUTHENTICATOR_PASSWORD:=changeme}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<EOSQL
    CREATE ROLE authenticator NOINHERIT LOGIN PASSWORD '${AUTHENTICATOR_PASSWORD}';
    GRANT web_anon TO authenticator;
EOSQL
