# Site Settings

**Status: Under Consideration**

## Problem Description

At several points with this project, we've built features that we've wanted to easily enable and disable in different environments, from a UI, without restarting the server.

## Requirements

- **Admin-only** - only superusers need access
- **Django Admin** - would prefer the UI to be in Django admin
- **No Migrations** - adding a new setting mustn't create a migration
- **No Restarts** - changing a setting mustn't require a server restart
- **No New Services** - database only, no Redis etc
- **Per-Environment Defaults** - different default values for dev vs prod
- **Boolean flags for now** - other types possible later

## Options

| Approach                                                         | No Migrations | No Restarts | Notes                                |
| ---------------------------------------------------------------- | ------------- | ----------- | ------------------------------------ |
| Environment variables                                            | ✅            | ❌          | Requires restart                     |
| Custom singleton model                                           | ❌            | ✅          | Simple, full control                 |
| Custom key-value store                                           | ✅            | ✅          | More complex admin UI                |
| [django-constance](https://github.com/jazzband/django-constance) | ✅            | ✅          | Mature library, nice admin UI        |
| [django-waffle](https://github.com/django-waffle/django-waffle)  | ✅            | ✅          | Overkill unless needing rollouts/A/B |

## django-constance Details

### Setup

```python
# settings/base.py
INSTALLED_APPS = [
    ...
    'constance',
]

CONSTANCE_BACKEND = 'constance.backends.database.DatabaseBackend'

CONSTANCE_CONFIG = {
    'ENABLE_FEATURE_X': (False, 'Description here', bool),
}
```

One-time migration creates its table. Adding/removing settings afterward requires no migrations.

### Usage

```python
from constance import config

if config.ENABLE_FEATURE_X:
    ...
```

### Per-Environment Defaults

Override in environment-specific settings:

```python
# settings/dev.py
CONSTANCE_CONFIG = {
    'ENABLE_FEATURE_X': (True, 'Description here', bool),  # On in dev
}
```

### Testing

```python
# settings/test.py
CONSTANCE_BACKEND = 'constance.backends.memory.MemoryBackend'
```
