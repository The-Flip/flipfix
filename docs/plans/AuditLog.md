# Audit Log Requirements

This document describes the requirements for audit logging and compares implementation options.

## Background

The museum director wants to track what volunteer maintainers are doing in the system. From [GitHub Issue #33](https://github.com/deanmoses/the_flip/issues/33):

> The museum director, William, tries to turn volunteers loose to do things, but he'd like to know what they did.

The audit trail should show:
 - who created/modified records
 - when
 - what was changed

---

## Requirements

### Works on Dev DB

The auditing package must work not only on Postgres but also on localhost dev SQLite databases.

### Revert / Restore

It would be nice to have the ability to click and restore a record to a previous point in time, all things being equal (they never are).

### Storage Impact

Audit logging must not meaningfully affect hosting  costs (the concern is that it might, due to increased database growth).

See database growth projections before this feature in [Hosting Requirements](./Hosting.md).

### Integration & Maintenance Costs

We want the integration and maintenance costs to be as low as possible.  Weight will be given to:
 - Least amount of custom code we must own (such as boilerplate code, custom diff viewers, etc)
 - Least number of migrations
 - Least amount of effort to audit each subsequent model

### Performance

We don't want this to affect the performance of writing data.  At least, weight will be given to packages that affect performance the least.

### Viability

We want a package that is:
 - actively maintained (as measured by recent commits)
 - used by lots of people
 - established, has a long history

### Models to Audit

Audit models that can be created or modified by maintainers through the application:

| Model | Create | Update | Why Audit |
|-------|--------|--------|-----------|
| **ProblemReport** | Yes | Yes (status, description) | Track who reported problems and who closed them |
| **LogEntry** | Yes | Yes (text, work_date, maintainers) | Track who logged work and any corrections |
| **LogEntryMedia** | Yes | Yes (delete) | Track who uploaded/deleted photos and videos |
| **MachineInstance** | Yes | Yes (status, location, details) | Track status changes and location moves |
| **MachineModel** | Yes | Yes (name, manufacturer, etc.) | Track edits to machine catalog information |

### Models NOT to Audit

Do not audit models that are admin-only or cannot be changed by maintainers.  This includes:

| Model | Reason |
|-------|--------|
| Location | Admin-only; maintainers can only select existing locations |
| WebhookEndpoint | Admin-only; webhook configuration |
| WebhookSettings | Admin-only; singleton settings |
| Maintainer | Admin-only; user profile management |
| User | Admin-only; Django auth |
| Invitation | Admin-only; invitation management |

### Non-Requirements

- **SQL queries against historical data**: Not needed. We don't need to run aggregate queries like "how many status changes happened last month" against the audit tables.

---

## Package Comparison

Both packages are maintained by [Jazzband](https://jazzband.co/), a collaborative community for Django packages.

### Philosophy

**django-auditlog**: "What changed?" — Lightweight audit trail. Stores only the diff (changed fields as JSON) in a single table. Created explicitly as a lightweight alternative when full version control was "excessive and expensive."

**django-simple-history**: "What was the state?" — Full version control. Stores complete snapshots of each record in per-model history tables. Enables rollback and time-travel queries.

### Contenders

- **[django-auditlog](https://github.com/jazzband/django-auditlog)**: Lightweight audit trail that stores only changed fields as JSON diffs in a single table.
- **[django-simple-history](https://github.com/jazzband/django-simple-history)**: Full version control that stores complete snapshots of each record, enabling rollback and time-travel queries.

### Comparison

|  | **django-auditlog** | **django-simple-history** |
|---|---|---|
| [Supports PostgreSQL & SQLite](#works-on-dev-db) | ✅ | ✅ |
| [No Increase in Hosting Cost](#storage-impact) | ✅ (~7MB over 3 years) | ✅ (~20MB over 3 years) |
| [Write Performance](#performance) | ✅ 1 INSERT + diff calculation | ✅ 1 INSERT (row copy) |
| [Supports Rollback](#revert--restore) | ❌ | ✅ Built-in revert to any previous version |
| Built-in Admin Diff View | ✅ Field/From/To table | ✅ Select two versions to compare |
| [Model Changes Required](#integration--maintenance-costs) | ❌ None (settings-based) | ✅ Add `history = HistoricalRecords()` to each model |
| [Number of Migrations](#integration--maintenance-costs) | 1 (single `auditlog_logentry` table) | 1 per tracked model (5 migrations for 5 models) |
| [Settings Configuration](#integration--maintenance-costs) | List models in `AUDITLOG_INCLUDE_TRACKING_MODELS` | Add to `INSTALLED_APPS` only |
| [Admin Changes](#integration--maintenance-costs) | Add `AuditlogHistoryAdminMixin` | Change base class to `SimpleHistoryAdmin` |
| [Template Code for Display](#integration--maintenance-costs) | ~10 lines (iterate `changes_dict`) | ~12 lines (use `diff_against()`) |
| [Ongoing Maintenance](#integration--maintenance-costs) | Add model name to settings when adding new audited models | Add `history` field to new audited models |
| [Actively Maintained](#viability) | ✅ v3.3.0 released Oct 2025 | ✅ v3.10.1 released Jun 2025 |
| [Popularity](#viability) (PyPI downloads/month) | 712K | 2.2M |
| [GitHub Stars](#viability) | 1.3K | 2.4K |
| [Project Age](#viability) | since 2013 |  since 2011 |

### Storage Model

| Aspect | django-auditlog | django-simple-history |
|--------|-----------------|----------------------|
| **Table structure** | Single `auditlog_logentry` table for ALL models | Separate `_history` table per model |
| **What's stored** | JSON diff of changed fields only | Full snapshot of entire record |
| **Per-change size** | ~100-500 bytes | Full row size (varies by model) |
| [**Affect on Hosting Cost**](#storage-impact) | None | None |
| **Query efficiency** | Generic foreign key (content_type + object_pk) | Direct foreign key to original model |

### Example: What Gets Stored

When a ProblemReport status changes from "open" to "closed":

| django-auditlog | django-simple-history |
|-----------------|----------------------|
| `{"status": ["open", "closed"]}` + actor, timestamp, action type | Full copy of the ProblemReport row (all fields) + `history_user`, `history_date`, `history_type` |
