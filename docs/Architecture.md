# Architecture

This document describes:

- The [Django apps](#apps) that organize the codebase
- The [Railway services](#services) that run in production.

## Apps

### `core`

Shared helpers that don't belong to a single domain app: decorators, custom admin mixins, base templates, date utilities, etc. As well as cross-domain composition, like global feed/home/dashboard orchestration.

### `accounts`

Wraps Django's `AUTH_USER_MODEL` with the Maintainer profile.

### `catalog`

The catalog of pinball machines: Machine Models and Machine Instances.

### `maintenance`

Problem Reports and Log Entries.

### `parts`

Requests for replacement parts.

### `wiki`

Wiki for maintainer documentation. Supports templates that pre-fill create forms for problems, logs, and part requests.

### `discord`

Discord integration with two main features:

- **Outbound webhooks**: Posts notifications to Discord when events occur (problem reports, log entries, parts requests)
- **Inbound bot**: Listens to a configured Discord channel and creates tickets from employee messages

## App Dependencies

We try to keep apps separated at all layers, including views and forms. Cross-app imports are sometimes necessary for pragmatic reasons, but should not be the default. The "Model dependencies" column is strict — `models.py` must only contain relational references to the listed apps. The "Also used in views" column lists additional apps referenced at the view/form/template layer where full separation wasn't practical.

| App             | Model dependencies      | Also used in views          |
| --------------- | ----------------------- | --------------------------- |
| **core**        | -                       |                             |
| **accounts**    | core                    |                             |
| **wiki**        | core                    |                             |
| **catalog**     | core                    | maintenance                 |
| **maintenance** | core, accounts, catalog |                             |
| **parts**       | core, accounts, catalog | maintenance                 |
| **discord**     | core, accounts          | catalog, maintenance, parts |

## Services

Railway runs these services:

### Web Application

- Serves the website and handles user requests
- **Static files** (CSS, JS, app images): Served by [WhiteNoise](https://whitenoise.readthedocs.io/), which indexes files at startup and serves them with caching headers
- **Media files** (user-uploaded photos and videos): Served by a custom Django view (`serve_media`) that reads from `MEDIA_ROOT`. WhiteNoise can't serve these because WhiteNoise only indexes files at startup, not dynamically uploaded content.

### Background Worker

- Handles async tasks, like video transcoding and webhook delivery

### Persistent File Storage

- Store uploaded photos and videos
- _In prod_: a persistent disk attached to the web application
- _In dev_: the local project directory

### Database

- Stores all application data
- _In prod_: PostgreSQL
- _In dev_: SQLite
