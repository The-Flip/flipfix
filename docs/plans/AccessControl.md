# Access Control Plan

This is a plan to make this project's access control follow Django best practices.

## Current State

- Pinball machine maintainers need access to the end user site but NOT Django admin; however, they _DO_ have access to Django admin.
- Maintainer role is implied by `User.is_staff=True`; a `Maintainer` profile is auto-created for staff users (signal).
- All maintainer-only views/APIs use `UserPassesTestMixin` with `user.is_staff` checks.
- Registration and invitation flows set `is_staff=True` for maintainers; shared terminals also set `is_staff=True`.
- Invitations are managed in Django admin (`InvitationAdmin` in `accounts/admin.py`, superuser-only). Superusers create invitations, which generates registration links sent to new maintainers.
- Discord record creation relies on `Maintainer` profiles, which are auto-created for staff users. Discord auto-links by matching usernames to existing Maintainer profiles (no direct `is_staff` dependency).
- No Django Groups or custom permissions are defined for maintainers; `is_staff` is overloaded as the role flag.

## Best Practice Direction

- Use Django's permission system with an explicit maintainer role: a "Maintainers" group carrying `accounts.can_access_maintainer_portal` permission (defined on the `Maintainer` model in the `accounts` app).
- Reserve `is_staff` for Django admin site access only; reserve `is_superuser` for full control.
- Centralize authorization checks in capability-based mixins following a `Can<Capability>Mixin` pattern (e.g., `CanAccessMaintainerPortalMixin`, `CanManageTerminalsMixin` etc), not role-based checks like `is_staff`.
- Ensure maintainer profiles are created/linked independent of `is_staff`.

## Rationale

- Aligns with Django conventions (staff ⇒ admin-site gate, permissions ⇒ app access).
- Makes authorization auditable and explicit; avoids over-granting admin access.
- Supports non-staff maintainers (e.g., Discord users) without admin exposure.
- Simplifies future role changes (add granular perms/groups without reusing `is_staff`).

## Benefits

- Clear separation of duties: admin access vs maintainer app access.
- Principle of least privilege: maintainers no longer need admin-site rights.
- Easier auditing and onboarding via groups/permissions.
- Extensible: can add finer-grained permissions later.

## Drawbacks / Risks

- Migration effort: many views/tests assume `is_staff`; must update consistently.
- Existing staff users may lose access if the new permission/group is not seeded correctly.
- Discord linkage flows must ensure maintainer profiles exist without staff reliance (note: Discord already works this way—it matches usernames to `Maintainer` profiles, not `is_staff`).

## Implementation Plan

**Important**: we will implement, test and deploy to prodution Phase 1 before beginning Phase 2. This ensures the refactoring is stable before changing authorization logic.

### Phase 1 — Centralize auth checks (no behavior change yet)

- Current: Each maintainer view repeats `LoginRequiredMixin` + `UserPassesTestMixin` with `test_func` returning `user.is_staff`; some inline handlers manually check `is_staff`. Terminal management views use `SuperuserRequiredMixin` (role-based naming). `MachineBulkQRCodeView` incorrectly requires superuser when it should only require maintainer access.
- Goal: Uniform, readable guards using capability-based naming (`Can<Capability>Mixin` pattern) that don't require every view to reimplement `test_func`.
- Steps:
  1. Add `CanAccessMaintainerPortalMixin` to `core/mixins.py`. It should wrap `LoginRequiredMixin` + `UserPassesTestMixin` internally, encapsulating the existing rule (for now, still `is_staff` or superuser). Behavior: unauthenticated users → redirect to login; authenticated but unauthorized → 403.
  2. Replace per-view `test_func` implementations and manual `if not user.is_staff` checks with the new mixin. This includes `MachineBulkQRCodeView` in `maintenance/views.py`, which will change from superuser-only to maintainer access (intentional fix).
  3. Rename `SuperuserRequiredMixin` (which is only used to manage terminals) to `CanManageTerminalsMixin` (move to `core/mixins.py`); update terminal management views to use it. Behavior unchanged (still checks `is_superuser`). Note: `admin_debug_dashboard` in `core/admin_views.py` will remain as a direct `is_superuser` check (it's an admin-only debug view).
  4. Update tests to assert the mixin-based access behavior (still using `is_staff`/`is_superuser`), ensuring no regressions. Add explicit test coverage for `MachineBulkQRCodeView` and terminal management views.
  5. Deploy to production and verify no access regressions.
- Rationale: Reduces duplication, clarifies intent (capability-based names are clearer than role-based), and concentrates the rules in one place for safer future changes. The `Can<Capability>Mixin` pattern is extensible for future permissions.

### Phase 2 — Switch to permissions/groups (allow non-staff maintainers)

- Define role
  - Create a "Maintainers" group and custom permission `accounts.can_access_maintainer_portal` on the `Maintainer` model.
  - Seed group and permission via data migration; add all existing maintainers to the group.
- Access checks
  - Update `CanAccessMaintainerPortalMixin` to use `user.has_perm('accounts.can_access_maintainer_portal')`. Django's `has_perm()` automatically returns `True` for superusers.
  - Keep view code unchanged beyond the mixin update.
- User lifecycle (update these views in `accounts/views.py`)
  - `self_register()`: create `Maintainer` profile, assign to Maintainers group; stop setting `is_staff`.
  - `invitation_register()`: same changes. The invitation admin page itself (`InvitationAdmin`) needs no changes—it's already superuser-only and just creates invitation records.
  - `TerminalCreateView`: create `Maintainer` profile, assign to Maintainers group; stop setting `is_staff`.
  - `is_superuser` unchanged.
- Signal cleanup
  - Remove `create_maintainer_for_staff` signal in `accounts/signals.py`. Currently it only creates Maintainer profiles when `is_staff=True`, which won't fire for non-staff maintainers. The registration views already explicitly call `Maintainer.objects.get_or_create()`, so the signal is redundant.
- Discord integration
  - No changes needed. Discord already links by matching usernames to `Maintainer` profiles, with no `is_staff` dependency.
- Tests and fixtures
  - Update `core/test_utils.py` helpers (`create_staff_user()`, etc.) to create maintainer users via group assignment instead of `is_staff`.
  - Adjust tests that assert `is_staff` to assert maintainer permission/group and access behavior.
- Rollout checks
  - Verify maintainer flows (web + Discord) work for non-staff maintainers.
  - Verify admin access still works for superusers.

### Phase 3 - Data Cleanup

After Phase 2 is shipped and stable, manually remove `is_staff=True` from maintainer accounts that don't need Django admin access.
