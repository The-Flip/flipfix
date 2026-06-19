# Internal API

Flipfix exposes a JSON API for internal services (e.g., signage apps, dashboards, power
monitoring) that need machine data. Most endpoints are read-only; a small write surface exists for
trusted services and is gated behind a per-key **write** capability.

## Authentication

All API endpoints require a **Bearer token** in the `Authorization` header.

### Obtaining a key

1. Go to **Django Admin > Core > API keys**
2. Click **Add API key**
3. Enter an `app_name` (e.g., `signage-app`) — this is for your reference
4. Save — a 64-character hex key is auto-generated
5. Copy the key from the detail page (it's read-only after creation)

To rotate a key: create a new one, update your client, then delete the old one.

### Read vs. write keys

Every valid key may call the read endpoints. Write endpoints additionally require the key's
**Can write** flag to be enabled (set it on the API key in Django Admin). A read-only key that
calls a write endpoint gets `403`. Grant write access only to trusted services that genuinely need
to mutate data.

### Sending the key

```
Authorization: Bearer <your-api-key>
```

### Error responses

| Status | Meaning                                             |
| ------ | --------------------------------------------------- |
| 400    | Invalid request body (write endpoints)              |
| 401    | Missing or malformed `Authorization` header         |
| 403    | API key not recognized, or not authorized for write |
| 404    | Resource not found                                  |

All error responses return JSON:

```json
{ "success": false, "error": "description" }
```

## Endpoints

### `GET /api/v1/machines/`

Returns all machines with model and location info.

**Example request:**

```bash
curl -H "Authorization: Bearer <key>" https://flipfix.example.com/api/v1/machines/
```

**Example response:**

```json
{
  "machines": [
    {
      "asset_id": "M0001",
      "name": "Medieval Madness",
      "short_name": "Med Madness",
      "slug": "medieval-madness",
      "serial_number": "SN-12345",
      "operational_status": "good",
      "location": "Main Floor",
      "model": {
        "name": "Medieval Madness",
        "manufacturer": "Williams",
        "year": 1997,
        "month": 6,
        "era": "SS",
        "system": "WPC-95",
        "scoring": "points",
        "flipper_count": 2,
        "ipdb_id": 4032,
        "pinside_rating": 9.1
      }
    }
  ]
}
```

**Field reference:**

| Field                  | Type        | Description                                     |
| ---------------------- | ----------- | ----------------------------------------------- |
| `asset_id`             | string      | Unique asset identifier (e.g., `M0001`)         |
| `name`                 | string      | Display name of the machine instance            |
| `short_name`           | string/null | Short name for compact displays                 |
| `slug`                 | string      | URL-friendly identifier                         |
| `serial_number`        | string      | Manufacturer serial number (may be empty)       |
| `operational_status`   | string      | One of: `good`, `fixing`, `broken`, `unknown`   |
| `location`             | string/null | Location name, or null if unassigned            |
| `model.name`           | string      | Machine model name                              |
| `model.manufacturer`   | string      | Manufacturer name (may be empty)                |
| `model.year`           | int/null    | Year of manufacture                             |
| `model.month`          | int/null    | Month of manufacture (1–12)                     |
| `model.era`            | string      | Technology era: `PM`, `EM`, `SS` (may be empty) |
| `model.system`         | string      | Electronic system, e.g. `WPC-95` (may be empty) |
| `model.scoring`        | string      | Scoring type (may be empty)                     |
| `model.flipper_count`  | int/null    | Number of flippers                              |
| `model.ipdb_id`        | int/null    | Internet Pinball Database ID                    |
| `model.pinside_rating` | float/null  | Pinside rating (0–10)                           |

Machines are ordered alphabetically by model sort name (leading articles like "The" are stripped for sorting).

### `GET /api/v1/machines/<asset_id>/`

Returns a single machine by its asset ID. The lookup is case-insensitive.

**Example request:**

```bash
curl -H "Authorization: Bearer <key>" https://flipfix.example.com/api/v1/machines/M0001/
```

**Example response:**

```json
{
  "machine": {
    "asset_id": "M0001",
    "name": "Medieval Madness",
    "short_name": "Med Madness",
    "slug": "medieval-madness",
    "serial_number": "SN-12345",
    "operational_status": "good",
    "location": "Main Floor",
    "model": {
      "name": "Medieval Madness",
      "manufacturer": "Williams",
      "year": 1997,
      "month": 6,
      "era": "SS",
      "system": "WPC-95",
      "scoring": "points",
      "flipper_count": 2,
      "ipdb_id": 4032,
      "pinside_rating": 9.1
    }
  }
}
```

Returns 404 if no machine matches the given asset ID:

```json
{ "success": false, "error": "Machine with asset ID 'M9999' not found" }
```

The response fields are the same as the list endpoint — see the [field reference](#get-apiv1machines) above.

### `POST /api/v1/machines/<asset_id>/problem-reports/`

**Write endpoint** — requires a key with the **write** capability (see [Read vs. write
keys](#read-vs-write-keys)).

Files a problem report against a machine, and optionally marks the machine `broken` in the same
transaction. Designed for automated services such as [juice](https://github.com/The-Flip/juice)
power monitoring, which files an `unplayable` report and trips the machine to `broken` when it
auto-cuts power on a sustained overload.

**Request body** (all fields optional):

| Field              | Type    | Default | Description                                                         |
| ------------------ | ------- | ------- | ------------------------------------------------------------------- |
| `priority`         | string  | `minor` | One of `untriaged`, `unplayable`, `major`, `minor`, `task`          |
| `problem_type`     | string  | `other` | One of `stuck_ball`, `no_credits`, `other`                          |
| `description`      | string  | `""`    | Free-text description of the problem                                |
| `occurred_at`      | string  | now     | ISO-8601 datetime of when the problem occurred                      |
| `reported_by_name` | string  | `""`    | Attribution for the reporter (e.g. service name)                    |
| `mark_broken`      | boolean | `false` | When `true`, also sets `operational_status = broken` on the machine |

**Example request:**

```bash
curl -X POST \
  -H "Authorization: Bearer <write-key>" \
  -H "Content-Type: application/json" \
  -d '{
        "priority": "unplayable",
        "description": "Auto power-off: sustained overload (175W vs 49W baseline)",
        "reported_by_name": "Juice (automated overload detection)",
        "mark_broken": true
      }' \
  https://flipfix.example.com/api/v1/machines/M0001/problem-reports/
```

**Example response (`201 Created`):**

```json
{
  "problem_report": {
    "id": 42,
    "machine_asset_id": "M0001",
    "status": "open",
    "priority": "unplayable",
    "problem_type": "other",
    "description": "Auto power-off: sustained overload (175W vs 49W baseline)",
    "reported_by_name": "Juice (automated overload detection)",
    "occurred_at": "2026-06-14T21:41:25+00:00",
    "created_at": "2026-06-14T21:41:25+00:00"
  }
}
```

**Idempotency.** If `priority` is `unplayable` and the machine already has an **open** `unplayable`
report, that existing report is returned with `200 OK` instead of creating a duplicate — so a
service that re-detects the same fault won't pile up reports. Other priorities always create a new
report.

When `mark_broken` is `true`, the status change is written through the machine's history (a "Status
changed → Broken" log entry is recorded automatically). Closing the report does **not** revert the
machine to `good` — that's left to a maintainer.

### `POST /api/v1/problem-reports/<pk>/log-entries/`

**Write endpoint** — requires a key with the **write** capability (see [Read vs. write
keys](#read-vs-write-keys)).

Appends a log entry to an existing problem report. This is the companion to the idempotent
problem-report create above: when a recurrence (e.g. juice shutting an already-broken machine down
_again_) hits the `200` idempotent path and creates no new report, the caller uses the returned
`problem_report.id` here to record what happened.

**Request body:**

| Field              | Type   | Default        | Description                                       |
| ------------------ | ------ | -------------- | ------------------------------------------------- |
| `text`             | string | **required**   | The log entry body (must be non-empty)            |
| `occurred_at`      | string | now            | ISO-8601 datetime of when the work/event occurred |
| `reported_by_name` | string | key `app_name` | Display name for the author (max 120 chars)       |

`reported_by_name` is stored as the entry's `maintainer_names`. When omitted, it defaults to the API
key's `app_name`, so an entry always carries attribution.

**Example request:**

```bash
curl -X POST \
  -H "Authorization: Bearer <write-key>" \
  -H "Content-Type: application/json" \
  -d '{
        "text": "Auto power-off recurrence: 182W peak vs 49W baseline over 3m12s",
        "reported_by_name": "Juice"
      }' \
  https://flipfix.example.com/api/v1/problem-reports/42/log-entries/
```

**Example response (`201 Created`):**

```json
{
  "log_entry": {
    "id": 7,
    "problem_report_id": 42,
    "machine_asset_id": "M0001",
    "text": "Auto power-off recurrence: 182W peak vs 49W baseline over 3m12s",
    "maintainer_names": "Juice",
    "occurred_at": "2026-06-19T15:51:00+00:00",
    "created_at": "2026-06-19T15:51:00+00:00"
  }
}
```

Returns `404` if no problem report has the given `pk`, and `400` for a missing/empty `text`, an
unparseable `occurred_at`, malformed JSON, or a `reported_by_name` longer than 120 characters. The
log entry is linked to the report's machine, so it appears on both the report and the machine
timeline (and posts to the Discord #logs channel like any other log entry).

## Versioning

Endpoints are prefixed with `/api/v1/`. Breaking changes will use a new version prefix (`/api/v2/`, etc.).

## Regenerating sample data from production

The committed sample-data fixture (`docs/sample_data/records/machines.json`) is what
`make sample-data` loads into local dev and CI databases. Maintainers can refresh it from the
live collection using the machine list endpoint:

```bash
export SAMPLE_DATA_API_KEY=<a key from Django Admin → Core → API keys>
python manage.py pull_sample_machines        # rewrites the fixture
# or preview first:
python manage.py pull_sample_machines --dry-run
```

Config: `--url` / `$SAMPLE_DATA_API_URL` (defaults to production) and `--api-key` /
`$SAMPLE_DATA_API_KEY`. The command only reads the API and writes the file — it never touches
the database, so dev/test stay fully offline. Fields the API does not expose (e.g.
`acquisition_notes`, owner) are **not** regenerated, which keeps that data out of the public repo.

Review the diff and commit the updated fixture; then `make sample-data` (on a fresh SQLite DB)
loads it.
