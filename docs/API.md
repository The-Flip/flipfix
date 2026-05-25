# Internal API

Flipfix exposes a read-only JSON API for internal services (e.g., signage apps, dashboards) that need machine data.

## Authentication

All API endpoints require a **Bearer token** in the `Authorization` header.

### Obtaining a key

1. Go to **Django Admin > Core > API keys**
2. Click **Add API key**
3. Enter an `app_name` (e.g., `signage-app`) — this is for your reference
4. Save — a 64-character hex key is auto-generated
5. Copy the key from the detail page (it's read-only after creation)

To rotate a key: create a new one, update your client, then delete the old one.

### Sending the key

```
Authorization: Bearer <your-api-key>
```

### Error responses

| Status | Meaning                                     |
| ------ | ------------------------------------------- |
| 401    | Missing or malformed `Authorization` header |
| 403    | API key not recognized                      |

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
