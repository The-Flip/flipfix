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

Audit logging must not meaningfully affect hosting costs (the concern is that it might, due to increased database growth).

See database growth projections before this feature in [Hosting Requirements](./Hosting.md).

### Integration & Maintenance Costs

We want the integration and maintenance costs to be as low as possible. Weight will be given to:

- Least amount of custom code we must own (such as boilerplate code, custom diff viewers, etc)
- Least number of migrations
- Least amount of effort to audit each subsequent model

### Performance

We don't want this to affect the performance of writing data. At least, weight will be given to packages that affect performance the least.

### Viability

We want a package that is:

- actively maintained (as measured by recent commits)
- used by lots of people
- established, has a long history

### Models to Audit

Audit models that can be created or modified by maintainers through the application:

| Model               | Create | Update                               | Why Audit                                       |
| ------------------- | ------ | ------------------------------------ | ----------------------------------------------- |
| **ProblemReport**   | Yes    | Yes (status, description)            | Track who reported problems and who closed them |
| **LogEntry**        | Yes    | Yes (text, occurred_at, maintainers) | Track who logged work and any corrections       |
| **LogEntryMedia**   | Yes    | Yes (delete)                         | Track who uploaded/deleted photos and videos    |
| **MachineInstance** | Yes    | Yes (status, location, details)      | Track status changes and location moves         |
| **MachineModel**    | Yes    | Yes (name, manufacturer, etc.)       | Track edits to machine catalog information      |

### Models NOT to Audit

Do not audit models that are admin-only or cannot be changed by maintainers. This includes:

| Model           | Reason                                                     |
| --------------- | ---------------------------------------------------------- |
| Location        | Admin-only; maintainers can only select existing locations |
| DiscordUserLink | Admin-only; Discord user mapping                           |
| Maintainer      | Admin-only; user profile management                        |
| User            | Admin-only; Django auth                                    |
| Invitation      | Admin-only; invitation management                          |

### Front-End Display

The audit trail should be displayed at the bottom of detail pages in the maintainer-facing app (not just in Django admin). Considerations:

- Out-of-the-box UI components for displaying history
- Customizable templates (HTML/CSS) to match the app's look and feel

### Non-Requirements

- **SQL queries against historical data**: Not needed. We don't need to run aggregate queries like "how many status changes happened last month" against the audit tables.

---

## Package Comparison

### Contenders

- **[django-auditlog](https://github.com/jazzband/django-auditlog)**: Lightweight audit trail that stores only changed fields as JSON diffs in a single table. Maintained by [Jazzband](https://jazzband.co/).
- **[django-simple-history](https://github.com/jazzband/django-simple-history)**: Full version control that stores complete snapshots of each record, enabling rollback and time-travel queries. Maintained by [Jazzband](https://jazzband.co/).
- **[django-reversion](https://github.com/etianen/django-reversion)**: Version control system that stores serialized model snapshots, with strong admin integration for recovering deleted objects.

### Philosophy

| Package                   | Philosophy                                                                                                                                                                                                           |
| ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **django-auditlog**       | "What changed?" — Lightweight audit trail. Stores only the diff (changed fields as JSON) in a single table. Created explicitly as a lightweight alternative when full version control was "excessive and expensive." |
| **django-simple-history** | "What was the state?" — Full version control. Stores complete snapshots of each record in per-model history tables. Enables rollback and time-travel queries.                                                        |
| **django-reversion**      | "Version control for models" — Stores serialized snapshots with focus on admin-based recovery of deleted objects and rollback. Requires wrapping views/code in revision blocks.                                      |

### Features

|                                                  | **django-auditlog**            | **django-simple-history** | **django-reversion**                 |
| ------------------------------------------------ | ------------------------------ | ------------------------- | ------------------------------------ |
| [Supports PostgreSQL & SQLite](#works-on-dev-db) | ✅                             | ✅                        | ✅                                   |
| [No Increase in Hosting Cost](#storage-impact)   | ✅ (~7MB over 3 years)         | ✅ (~20MB over 3 years)   | ✅ (~20MB over 3 years)              |
| [Write Performance](#performance)                | ✅ 1 INSERT + diff calculation | ✅ 1 INSERT (row copy)    | ✅ 1 INSERT (serialized snapshot)    |
| [Supports Rollback](#revert--restore)            | ❌                             | ✅ Built-in revert        | ✅ Built-in revert + recover deleted |

### Maintainability

|                                                              | **django-auditlog**                | **django-simple-history**                         | **django-reversion**                                                                              |
| ------------------------------------------------------------ | ---------------------------------- | ------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Built-in Admin Diff View                                     | ✅ Field/From/To table             | ✅ Select two versions to compare                 | ⚠️ Requires [django-reversion-compare](https://pypi.org/project/django-reversion-compare/) add-on |
| [Model Changes Required](#integration--maintenance-costs)    | None (settings-based)              | Add `history = HistoricalRecords()` to each model | None (register via admin or decorator)                                                            |
| [Number of Migrations](#integration--maintenance-costs)      | 1 (single table)                   | 1 per tracked model (5 migrations)                | 1 (single `reversion_*` tables)                                                                   |
| [Settings Configuration](#integration--maintenance-costs)    | List models in settings            | Add to `INSTALLED_APPS` only                      | Add to `INSTALLED_APPS` only                                                                      |
| [Admin Changes](#integration--maintenance-costs)             | Add `AuditlogHistoryAdminMixin`    | Change base class to `SimpleHistoryAdmin`         | Change base class to `VersionAdmin`                                                               |
| [Template Code for Display](#integration--maintenance-costs) | ~10 lines (iterate `changes_dict`) | ~12 lines (use `diff_against()`)                  | ~20+ lines (deserialize versions manually)                                                        |
| [Front-End Display](#front-end-display)                      | Custom templates (easy)            | Custom templates (easy)                           | Custom templates (harder - serialized data)                                                       |
| [Ongoing Maintenance](#integration--maintenance-costs)       | Add model name to settings         | Add `history` field to new models                 | Register new models in admin                                                                      |

### Viability

|                                                 | **django-auditlog**  | **django-simple-history** | **django-reversion** |
| ----------------------------------------------- | -------------------- | ------------------------- | -------------------- |
| [Actively Maintained](#viability)               | ✅ v3.3.0 (Oct 2025) | ✅ v3.10.1 (Jun 2025)     | ✅ v6.0.0 (Sep 2025) |
| [Popularity](#viability) (PyPI downloads/month) | 712K                 | 2.2M                      | 1.0M                 |
| [GitHub Stars](#viability)                      | 1.3K                 | 2.4K                      | 3.1K                 |
| [Project Age](#viability)                       | since 2013           | since 2011                | since 2010           |

### Storage Model

|                                               | django-auditlog                                 | django-simple-history                | django-reversion                                |
| --------------------------------------------- | ----------------------------------------------- | ------------------------------------ | ----------------------------------------------- |
| **Table structure**                           | Single `auditlog_logentry` table for ALL models | Separate `_history` table per model  | Single `reversion_version` table for ALL models |
| **What's stored**                             | JSON diff of changed fields only                | Full snapshot of entire record       | Serialized (JSON) snapshot of entire record     |
| **Per-change size**                           | ~100-500 bytes                                  | Full row size (varies by model)      | Full row size (serialized)                      |
| [**Affect on Hosting Cost**](#storage-impact) | None                                            | None                                 | None                                            |
| **Query efficiency**                          | Generic foreign key                             | Direct foreign key to original model | Generic foreign key                             |
| **Data format**                               | Human-readable JSON                             | Native Django fields                 | Serialized JSON (less queryable)                |

### Example: What Gets Stored

When a ProblemReport status changes from "open" to "closed":

| django-auditlog                                                  | django-simple-history                                                                            | django-reversion                                                                |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------- |
| `{"status": ["open", "closed"]}` + actor, timestamp, action type | Full copy of the ProblemReport row (all fields) + `history_user`, `history_date`, `history_type` | Serialized JSON of full ProblemReport + revision metadata (user, comment, date) |

---

## Analysis

### Why Not django-reversion?

Despite having the most GitHub stars and longest history, **django-reversion is not recommended** for this project:

- **Admin-focused**: Designed primarily for admin-based versioning (recovering deleted objects, comparing versions in Django admin), not for programmatic history access or front-end display.
- **Serialized storage**: Stores data as serialized/pickled objects rather than structured history tables. This makes the data less queryable and harder to work with in custom front-end templates.
- **Extra dependency for diffs**: Requires the separate [django-reversion-compare](https://pypi.org/project/django-reversion-compare/) add-on to show what changed between versions.

### Recommendation: Choose Between the Two Jazzband Packages

Both **django-auditlog** and **django-simple-history** are well-suited for this project:

- Modern, clean APIs designed for programmatic access
- Easy to display in custom front-end templates
- Well-documented with active communities

**Choose django-auditlog if:**

- Rollback capability is not needed
- You prefer zero model changes (settings-only configuration)
- Smaller storage footprint is appealing

**Choose django-simple-history if:**

- Rollback capability is important
- You want the most popular/widely-used option
- You don't mind adding one line per model

---

## Decision

**Package: django-simple-history**

Selected for:

- Built-in rollback capability
- Most popular option (2.2M downloads/month)
- Excellent admin integration with diff view
- Direct foreign keys for efficient queries

### UX Design

**Phase 1: Link to Admin**

- History icon in sidebar top-right corner (absolutely positioned)
- Desktop only (hidden on mobile)
- Tooltip on hover: "History"
- Links directly to Django admin history view for that object
- Zero custom front-end code required

**Phase 2: Quick Preview (Future)**

- On hover/click, show 3 most recent changes inline
- Link to full admin history view
- Provides "smell test" without leaving the page
