# Task and Log Entry Refactor

## Overview

Right now, this system is geared towards unauthenticated museum visitors scanning a QR code on a machine and filling out a form to submit a problem report.  Authenticated maintainers do work and add Problem Report Updates to log their work.

We want to refactor the system to support the workshop and storage workflows as described in MAINTENANCE_WORKFLOW.md in addition to the existing problem report workflow.

## Current State

- `ProblemReport` model - mostly geared towards visitor-reported issues on machines in service, though maintainers *can* submit them
- `ReportUpdate` model - for maintainer updates on problem reports

## Goals

Support three types of workflows:
1. **Machines in Service** - visitors report problems (existing workflow)
2. **Machines in Workshop** - maintainers create TODOs and log work.  This update is aimed at supporting this workflow.
3. **Machines in Storage** - maintainers track condition and maintenance history.  This update isn't aimed at supporting this workflow.  It will come in the future.

## Data Model Changes

### Model Renames

**`Task`** (renamed from `ProblemReport`)
- Represents both Problem Reports (visitor-created) *and* TODOs (maintainer-created)
- Fields:
  - All existing ProblemReport fields
  - `created_by_maintainer` (boolean) - distinguish TODO from Problem Report
  - `status` - keep existing open/closed (no new statuses)

**`LogEntry`** (renamed from `ReportUpdate`)
- Represents Problem Report Updates, TODO updates, *and* standalone work logs
- Fields:
  - `task` - ForeignKey to Task (null=True, blank=True)
    - When `task` is None, it's a standalone log entry
    - When `task` is set, it's an update to that task
  - All existing ReportUpdate fields, but `task` becomes optional

### Visibility

- All Tasks are visible read-only to public, no authentication required (existing behavior)
- All LogEntries are visible read-only to public, no authentication required (existing behavior)
- The public can create a Problem Report from the page accessible via QR code (existing behavior).  Keep the same visual display and labels; don't rename this form to Task.
- Authentication required to create Tasks or LogEntries from maintainer UI (existing behavior)

### Migration Strategy

1. Rename `ProblemReport` → `Task`
2. Rename `ReportUpdate` → `LogEntry`
3. Make `task` (formerly `report`) nullable
4. Update all foreign key relationships and related_names


## UI Changes

### Maintainer's Machine Detail Page

Replace current "Report a Problem" button with two new buttons:
- **"Create Task"** - creates a Task (can be TODO or Problem Report style)
- **"Log Work"** - creates a LogEntry (optionally associated with a Task)

### Create Task Flow

Form should support:
- All existing problem report fields
- Same permissions: anyone can create (public or maintainer)

### Log Work Flow

Form should have:
- Text field for work description (not required)
- Optional dropdown to associate with an open Task on this machine
- Machine status change option (existing functionality)

### Display Changes

- Machine Detail: Show both Tasks and LogEntries
- Rename "Latest Problem Reports" → "Latest Tasks"
- Add new section: "Recent Work Log" showing standalone LogEntries
- Keep existing status badges and UI patterns


## Legacy Data Import

### New Management Command

`python manage.py create_legacy_maintenance_records`

This replaces `create_sample_problem_reports.py` (but don't delete the old one yet).

**Data Sources:**
- `docs/legacy_data/Maintenance - Problems.csv`: these become Tasks
- `docs/legacy_data/Maintenance - Log entries.csv`: these become standalone Log Entries, not associated with a Task

**Import Rules:**
1. Respect dates from CSV (use `created_at` override)
2. Parse maintainer names and link to existing Maintainer records.  Exit with error if any maintainer cannot be matched.  Handle multi-maintainer entries (comma-separated in CSV).
3. The machines should already be created in `create_default_machines.py`.  Exit with error if any maintenance item references a machine that does not exist.

**CSV Columns:**
- Machine (string) - match to MachineInstance by name
- Date (datetime) - becomes LogEntry.created_at
- Notes (text) - becomes LogEntry.text
- Maintainers (comma-separated) - match to Maintainer records

## Implementation Checklist

### Phase 1: Data Model
- [ ] Create migration to rename ProblemReport → Task
- [ ] Add `created_by_maintainer` field to Task
- [ ] Create migration to rename ReportUpdate → LogEntry
- [ ] Make LogEntry.task nullable
- [ ] Update all model methods and properties
- [ ] Update related_name attributes

### Phase 2: Update Code References
- [ ] Update models.py - rename classes, update relationships
- [ ] Update forms.py - create TaskCreateForm, LogEntryCreateForm
- [ ] Update views.py - rename functions, update logic
- [ ] Update urls.py - update URL patterns
- [ ] Update templates - rename problem_report → task
- [ ] Update admin.py if it exists

### Phase 3: New Features
- [ ] Create "Create Task" view and form
- [ ] Create "Log Work" view and form
- [ ] Update Machine Detail page with new buttons
- [ ] Add "Recent Work Log" section to Machine Detail
- [ ] Update report/task list page to show Tasks

### Phase 4: Legacy Data Import
- [ ] Create management command `import_legacy_maintenance.py`
- [ ] Parse CSV date formats
- [ ] Match machines by name (case-insensitive)
- [ ] Match maintainers by name
- [ ] Handle missing machines (create or skip?)
- [ ] Handle missing maintainers (create generic "Unknown" maintainer?)
- [ ] Respect CSV dates in LogEntry.created_at

### Phase 5: Testing & Verification
- [ ] Test Task creation (public and maintainer)
- [ ] Test LogEntry creation (with and without Task association)
- [ ] Test Machine Detail page displays correctly
- [ ] Run legacy data import
- [ ] Verify imported data displays correctly
- [ ] Test all existing problem report workflows still work

## URL Structure

Current:
- `/reports/` - list all reports
- `/reports/<id>/` - report detail
- `/new_report/` - create report
- `/machines/<slug>/` - machine detail

Proposed:
- `/tasks/` - list all tasks (renamed from reports)
- `/tasks/<id>/` - task detail (renamed from report_detail)
- `/tasks/new/` - create task (renamed from report_create)
- `/machines/<slug>/` - machine detail
- `/machines/<slug>/log/` - NEW: create log entry

## Notes

- Keep existing QR code workflow intact (visitors can still report problems)
- "Problem Report" terminology stays in user-facing text for public visitors
- "Task" terminology for maintainers
- Maintain backward compatibility during transition
- Keep existing rate limiting on task creation
