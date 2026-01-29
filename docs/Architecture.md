# Architecture

This document describes:

- The [Django apps](#apps) that organize the codebase
- The [Railway services](#services) that run in production.

## Apps

### `core`

Shared helpers that don't belong to a single domain app: decorators, custom admin mixins, base templates, date utilities, etc.

### `accounts`

Wraps Django's `AUTH_USER_MODEL` with the Maintainer profile. Handles admin customization (list filters, field ordering) and any future features like maintainer onboarding or role management.

### `catalog`

Owns the catalog of pinball machines: Machine Models and Machine Instances. This includes public-facing metadata (educational content, credits, operational status). This app publishes read APIs/pages that the museum floor uses.

### `maintenance`

Owns Problem Reports and Log Entries. Encapsulates workflows such as auto-closing tasks when machines are marked "good", rate-limiting public problem report submissions.

### `parts`

Owns requests for replacement parts and their lifecycle tracking (requested → ordered → received).

### `discord`

Discord integration with two main features:

- **Outbound webhooks**: Posts notifications to Discord when events occur (problem reports, log entries, parts requests)
- **Inbound bot**: Listens to a configured Discord channel and creates tickets from employee messages

## App Dependencies

| App             | Depends On                                  |
| --------------- | ------------------------------------------- |
| **core**        | nothing                                     |
| **accounts**    | core                                        |
| **catalog**     | core                                        |
| **maintenance** | core, accounts, catalog                     |
| **parts**       | core, accounts, catalog, maintenance        |
| **discord**     | core, accounts, catalog, maintenance, parts |

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
