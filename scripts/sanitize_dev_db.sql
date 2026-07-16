-- Sanitize a freshly-restored production dump for safe local development use.
--
-- Run ONLY against the local dev database, never production. scripts/sync_prod.sh
-- runs this automatically after restoring the dump into the local Postgres
-- container. It is idempotent and safe to re-run.
--
-- Secret/history/out-of-scope table DATA is already excluded at dump time by
-- sync_prod.sh, so the TRUNCATEs below are belt-and-suspenders: they also make
-- this file correct if someone restores a full (un-excluded) dump. Missing
-- tables are skipped rather than erroring, so the file tolerates schema drift.

BEGIN;

-- 1. Empty every table whose data must never exist in a dev environment:
--    live secrets/credentials, sessions, background-job payloads, the
--    django-simple-history shadow tables (which duplicate every past value of
--    the PII scrubbed below), and the apps outside the "maintenance core" scope
--    (parts / wiki / comments / documents / discord).
-- Matched by table-name PATTERN rather than a hardcoded list, so new tables in a
-- dropped app (or a renamed one, e.g. constance_constance vs constance_config)
-- are covered automatically. Only whole apps that are entirely out of scope get a
-- prefix wildcard; the kept "catalog"/"maintenance"/"auth" apps are never
-- wildcarded — their few droppable tables are named explicitly. Every parent's
-- children fall under the same wildcard (or are *historical*), so
-- TRUNCATE ... CASCADE never reaches a kept core table.
DO $$
DECLARE
    tbl text;
BEGIN
    FOR tbl IN
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND (
               table_name LIKE '%historical%'          -- simple_history shadow tables
            OR table_name LIKE 'constance\_%'           -- dynamic settings (secrets)
            OR table_name LIKE 'oauth2\_provider\_%'    -- OAuth tokens/apps
            OR table_name LIKE 'oauth\_%'               -- app capability grants
            OR table_name LIKE 'django\_q\_%'           -- background-job payloads
            OR table_name LIKE 'parts\_%'               -- out-of-scope app
            OR table_name LIKE 'wiki\_%'                -- out-of-scope app
            OR table_name LIKE 'discord\_%'             -- out-of-scope app
            OR table_name IN (
                'core_apikey', 'accounts_invitation',
                'django_session', 'django_admin_log',
                'catalog_machinecomment', 'catalog_ownercomment',
                'catalog_ownerdocument'
            )
        )
    LOOP
        EXECUTE format('TRUNCATE TABLE public.%I RESTART IDENTITY CASCADE', tbl);
    END LOOP;
END $$;

-- 2. Scrub PII from the kept "maintenance core" tables.

-- Users: fake emails, drop names, mark passwords unusable. sync_prod.sh sets a
-- known dev password on a superuser afterwards so you can still log in.
UPDATE auth_user SET
    email      = 'user' || id || '@example.test',
    first_name = '',
    last_name  = '',
    password   = '!scrubbed';   -- '!' prefix = Django "unusable password"

-- Machine owners: clear all direct contact details.
UPDATE catalog_owner SET
    email             = '',
    phone             = '',
    address           = '',
    alternate_contact = '',
    notes             = '';

-- Visitor-submitted problem reports: clear reporter identity and request metadata.
UPDATE maintenance_problemreport SET
    reported_by_name    = '',
    reported_by_contact = '',
    device_info         = '',
    ip_address          = NULL;

COMMIT;
