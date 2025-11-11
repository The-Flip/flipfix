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

**`Task`** (renamed from `ProblemReport`): represents both Problem Reports *and* Tasks
- Fields:
  - All existing `ProblemReport` fields
  - `type` (CharField with choices, default='problem_report')
    - `'problem_report'` = Problem Report (usually visitor-reported but can also be reported by a maintainer, urgent, created via the existing public form accesible via QR code)
    - `'task'` = Task (maintainer-created TODO, usually less urgent than a problem report)
  - `status` - keep existing open/closed (no new statuses)

**`LogEntry`** (renamed from `ReportUpdate`): represents Problem Report Updates, TODO updates, *and* standalone work logs
- Fields:
  - `task` - ForeignKey to `Task` (null=True, blank=True)
    - When `task` is None, it's a standalone log entry
    - When `task` is set, it's an update to that task
  - `maintainer` - **REMOVED** (replaced by many-to-many relationship)
  - `maintainers` - ManyToManyField to Maintainer (NEW)
    - Supports multiple maintainers working together on a log entry
    - By default, populated with just the creating maintainer
    - Creator can select additional maintainers who participated in the work
  - All other existing ReportUpdate fields remain

### Visibility

- All Tasks are visible read-only to public, no authentication required (existing behavior)
- All LogEntries are visible read-only to public, no authentication required (existing behavior)
- The public can create a Problem Report from the page accessible via QR code (existing behavior).  Keep the same visual display and labels; don't rename this form to Task.
- Authentication required to create Tasks or LogEntries from maintainer UI (existing behavior)

### Migration Strategy

1. Rename `ProblemReport` → `Task`
2. Add `type` field (CharField with choices, default='problem_report')
   - All existing ProblemReports become Tasks with `type='problem_report'`
3. Rename `ReportUpdate` → `LogEntry`
4. Make `task` (formerly `report`) nullable
5. Change `maintainer` from ForeignKey to ManyToManyField `maintainers`
   - For existing LogEntries, migrate single maintainer to many-to-many
   - Handle null maintainer case (some updates may not have a maintainer)
6. Update all foreign key relationships and related_names


## UI Changes

### Public-Facing Pages (QR Code Workflow)

**URLs unchanged:**
- `/m/<slug>/` - public educational page (QR code target) - no changes

**URLs updated:**
- `/new_report/<slug>/` → `/tasks/new/<slug>/` - problem report form
  - Keep "Problem Report" **terminology** in templates and labels
  - Update URL and URL name for consistency with maintainer interface

**View updates (completed):**
- `machine_public_view` - query `Task` objects filtered by `type='problem_report'`
- `report_create` / `report_create_qr` views - create `Task` with `type='problem_report'`
- `ProblemReportCreateForm` - work with `Task` model, automatically set `type='problem_report'`
- Templates keep all "Problem Report" terminology (no "Task" terminology for public)

### Maintainer's Machine Detail Page

Replace current "Report a Problem" button with two new buttons:
- **"Create Task"** - creates a Task (can be TODO or Problem Report style)
- **"Log Work"** - creates a LogEntry (optionally associated with a Task)

### Create Task Flow

Form should support:
- All existing problem report fields
- Created Tasks will have `type='task'` (marking them as maintainer TODOs)
- Same permissions: anyone can create (public or maintainer)
- Note: Public visitors creating via QR code will continue to create Tasks with `type='problem_report'`

### Log Work Flow

Form should have:
- Text field for work description (not required)
- Optional dropdown to associate with an open Task on this machine
- **Multi-select for additional maintainers** (NEW)
  - By default, pre-selects only the current user
  - User can select additional maintainers who worked on this
  - Shows all active maintainers
- Machine status change option (existing functionality)

### Display Changes

Machine Detail page should show three sections in this order:

1. **"Problem Reports"** - Tasks where `type='problem_report'` (visitor-reported, urgent)
   - Show status, date, problem type/text, reporter
   - Sorted by date (newest first)

2. **"Tasks"** - Tasks where `type='task'` (maintainer-created TODOs)
   - Show status, date, description, creator
   - Sorted by date (newest first)

3. **"Work Log"** - ALL LogEntries for this machine
   - Show date, maintainers, work description, associated task (if any)
   - Includes both standalone entries AND entries associated with Tasks
   - Sorted by date (newest first)

Keep existing status badges and UI patterns


## Legacy Data Import

### New Management Command

`python manage.py import_legacy_maintenance_records`

This replaces `create_sample_problem_reports.py` (but don't delete the old one yet).

**Data Approach:**
- Unlike `create_default_machines.py` which has legacy data hardcoded in Python, this command **reads CSV files at runtime**
- Legacy data stays in CSV format for easier updating and maintenance, no need to re-munge data if/when the CSV gets updated

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
- [ ] Add `type` CharField field with choices (default='problem_report' for existing records)
- [ ] Create migration to rename ReportUpdate → LogEntry
- [ ] Make LogEntry.task nullable
- [ ] Change LogEntry.maintainer from ForeignKey to ManyToManyField maintainers
- [ ] Migrate existing single maintainer data to many-to-many relationship
- [ ] Update all model methods and properties
- [ ] Update related_name attributes
- [ ] Add queryset methods: Task.objects.problem_reports() and Task.objects.tasks()

### Phase 2: Update Code References
- [ ] Update models.py - rename classes, update relationships
- [ ] Update forms.py
  - [ ] Update ProblemReportCreateForm to work with Task model
  - [ ] Ensure form sets type='problem_report' for public submissions
  - [ ] Create LogEntryCreateForm for maintainer log entries
- [ ] Update views.py
  - [ ] Update report_create / report_create_qr to create Task objects
  - [ ] Update machine_public_view to query Task.objects.filter(type='problem_report')
  - [ ] Update report_detail to work with Task model
  - [ ] Update report_list to query Task objects
  - [ ] Rename view functions (report_* → task_* internally, but keep public URLs)
- [ ] Update urls.py
  - [ ] Keep public URLs unchanged (/m/<slug>/, /new_report/<slug>/)
  - [ ] Update internal URL names if needed
- [ ] Update templates
  - [ ] Keep "Problem Report" terminology in public-facing templates
  - [ ] Update variable names (report → task in context)
  - [ ] Update maintainer templates with "Task" and "Log Entry" terminology
- [ ] Update admin.py
  - [ ] Update imports: `ProblemReport` → `Task`, `ReportUpdate` → `LogEntry`
  - [ ] Update `ProblemReportAdmin` → `TaskAdmin`
    - [ ] Update list_display to show `type` field
    - [ ] Add list_filter for `type` field (problem_report vs task)
    - [ ] Update Meta verbose_name to "Task" / "Tasks"
  - [ ] Update `ReportUpdateAdmin` → `LogEntryAdmin`
    - [ ] Update list_display: `report` → `task`, `maintainer` → show maintainers (m2m)
    - [ ] Update search_fields: `report__` → `task__`
    - [ ] Handle many-to-many maintainers display
    - [ ] Update Meta verbose_name to "Log Entry" / "Log Entries"
  - [ ] Update custom ordering in `game_maintenance_order` dict:
    - [ ] 'Problem Reports' → 'Tasks'
    - [ ] 'Problem Report Updates' → 'Log Entries'

### Phase 3: New Features
- [ ] Create "Create Task" view and form
- [ ] Create "Log Work" view and form
- [ ] Update Machine Detail page with new buttons
- [ ] Add "Recent Work Log" section to Machine Detail
- [ ] Update report/task list page to show Tasks

### Phase 4: Legacy Data Import
- [ ] Create management command `import_legacy_maintenance_records.py`
  - [ ] Clean up CSVs automatically on first read
    - [ ] Use Python's csv module with proper quoting to handle multi-line fields
    - [ ] No need to rewrite files - just parse correctly in memory
  - [ ] Machine name matching strategy:
    - [ ] Create hardcoded mapping dictionary for known mismatches
    - [ ] First try: normalized match (ignore capitalization, whitespace, punctuation)
    - [ ] Second try: check hardcoded mapping dictionary (ignore capitalization, whitespace, punctuation)
    - [ ] Exit with clear error if no match found, showing available machine names
  - [ ] Parse CSV date formats (handle various formats like "10/4/2025 6:09 PM")
  - [ ] Match maintainers by name (normalize same way as machines)
  - [ ] Create LogEntries with correct dates (override created_at)
  - [ ] Associate multiple maintainers with each LogEntry

### Phase 5: Testing & Verification
- [ ] Test Task creation (public and maintainer)
- [ ] Test LogEntry creation (with and without Task association)
- [ ] Test Machine Detail page displays correctly
- [ ] Run legacy data import
- [ ] Verify imported data displays correctly
- [ ] Test all existing problem report workflows still work

## URL Structure

**Previous (before refactor):**
- `/reports/` - list all reports
- `/reports/<id>/` - report detail
- `/new_report/` - create report (general)
- `/new_report/<slug>/` - create report via QR code
- `/machines/<slug>/` - machine detail

**Updated (completed):**
- `/tasks/` - list all tasks (URL name: `task_list`)
- `/tasks/<id>/` - task detail (URL name: `task_detail`)
- `/tasks/new/` - create task (URL name: `task_create`)
- `/tasks/new/<slug>/` - create task via QR code (URL name: `task_create_qr`)
- `/machines/<slug>/` - machine detail (unchanged)
- `/machines/<slug>/log/` - NEW: create log entry (to be implemented in Phase 3)

**Note:** Public-facing templates continue to use "Problem Report" terminology even though URLs are now `/tasks/*`

## Notes

- Keep existing QR code workflow intact (visitors can still report problems)
- "Problem Report" terminology stays in user-facing text for public visitors
- "Task" terminology for maintainers
- Maintain backward compatibility during transition
- Keep existing rate limiting on task creation
