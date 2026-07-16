-- Sanitize a freshly-restored production dump for safe local development use.
--
-- Run ONLY against the local dev database, never production. scripts/sync_prod.sh
-- runs this automatically after restoring the dump into the local Postgres
-- container. It is idempotent and safe to re-run.
--
-- Policy: dev gets a realistic copy of production — including edit history,
-- parts, wiki, and comments — with only secrets/live credentials, session/job
-- state, Discord links, and owner documents withheld, and with personal PII
-- scrubbed from the tables that carry it (live rows AND their simple_history
-- shadow tables).
--
-- The withheld tables' DATA is already excluded at dump time by sync_prod.sh, so
-- the TRUNCATEs below are belt-and-suspenders: they also make this file correct
-- if someone restores a full (un-excluded) dump. Missing tables are skipped
-- rather than erroring, so the file tolerates schema drift.

BEGIN;

-- 1. Empty tables whose data must never exist in dev: live secrets/credentials,
--    OAuth tokens + app registrations, sessions, background-job payloads, Discord
--    account links, and owner documents (sensitive attachments — their files
--    aren't synced anyway). Matched by name PATTERN so new tables in a withheld
--    app are covered automatically; kept apps are never wildcarded.
DO $$
DECLARE
    tbl text;
BEGIN
    FOR tbl IN
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND (
               table_name LIKE 'constance\_%'          -- dynamic settings (secrets)
            OR table_name LIKE 'oauth2\_provider\_%'   -- OAuth tokens + app registrations
            OR table_name LIKE 'oauth\_%'              -- OAuth capability grants
            OR table_name LIKE 'django\_q\_%'          -- background-job payloads
            OR table_name LIKE 'discord\_%'            -- third-party account links
            OR table_name IN (
                'core_apikey', 'accounts_invitation',
                'django_session', 'django_admin_log',
                'catalog_ownerdocument', 'catalog_historicalownerdocument'
            )
        )
    LOOP
        EXECUTE format('TRUNCATE TABLE public.%I RESTART IDENTITY CASCADE', tbl);
    END LOOP;
END $$;

-- 2. Scrub PII from the tables that carry it — the live row AND its
--    simple_history shadow (which duplicates every past value).

-- Users: fake emails, drop names, mark passwords unusable. sync_prod.sh sets a
-- known dev password on a superuser afterwards so you can still log in.
-- (auth_user has no simple_history shadow table.)
UPDATE auth_user SET
    email      = 'user' || id || '@example.test',
    first_name = '',
    last_name  = '',
    password   = '!scrubbed';   -- '!' prefix = Django "unusable password"

-- Machine owners: clear all direct contact details (live + history).
UPDATE catalog_owner SET
    email = '', phone = '', address = '', alternate_contact = '', notes = '';
UPDATE catalog_historicalowner SET
    email = '', phone = '', address = '', alternate_contact = '', notes = '';

-- Visitor-submitted problem reports: clear reporter identity + request metadata
-- (live + history).
UPDATE maintenance_problemreport SET
    reported_by_name = '', reported_by_contact = '', device_info = '', ip_address = NULL;
UPDATE maintenance_historicalproblemreport SET
    reported_by_name = '', reported_by_contact = '', device_info = '', ip_address = NULL;

COMMIT;
