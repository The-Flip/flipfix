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

### `webhooks`
Manages web hook notifications to external services (Discord, Slack, etc.) when events occur. Configurable endpoints and per-event subscriptions.

## App Dependencies

| App | Depends On |
|-----|------------|
| **core** | nothing |
| **accounts** | core |
| **catalog** | core |
| **maintenance** | core, accounts, catalog |
| **parts** | core, accounts, catalog, maintenance |
| **webhooks** | core, maintenance, parts |

## Services
Railway runs these services:

### Web Application
- Serves the website and handles user requests

### Background Worker
- Handles async tasks, like video transcoding and webhook delivery

### Persistent File Storage
- Store uploaded photos and videos
- *In prod*: a persistent disk attached to the web application
- *In dev*: the local project directory

### Database
- Stores all application data
- *In prod*: PostgreSQL
- *In dev*: SQLite
