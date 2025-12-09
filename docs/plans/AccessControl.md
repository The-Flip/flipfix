# Access Control Plan

This is a plan to make this project's access control follow Django best practices.

## Current State
- Pinball machine maintainers need access to the end user site but NOT Django admin; however, they *DO* have access to Django admin.
- Maintainer role is implied by `User.is_staff=True`; a `Maintainer` profile is auto-created for staff users (signal).
- All maintainer-only views/APIs use `UserPassesTestMixin` with `user.is_staff` checks.
- Registration and invitation flows set `is_staff=True` for maintainers; shared terminals also set `is_staff=True`.
- Discord record creation relies on `Maintainer` profiles, which are auto-created for staff users. Discord auto-links by matching usernames to existing Maintainer profiles (no direct `is_staff` dependency).
- No Django Groups or custom permissions are defined for maintainers; `is_staff` is overloaded as the role flag.

## Best Practice Direction
- Use Django's permission system with an explicit maintainer role: a "Maintainers" group carrying `accounts.can_access_maintainer_portal` permission (defined on the `Maintainer` model in the `accounts` app).
- Reserve `is_staff` for Django admin site access only; reserve `is_superuser` for full control.
- Centralize authorization checks in a reusable baseline mixin (`MaintainerAccessRequiredMixin`) based on the permission, not `is_staff`.
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
- Current: Each maintainer view repeats `LoginRequiredMixin` + `UserPassesTestMixin` with `test_func` returning `user.is_staff`; some inline handlers manually check `is_staff`.
- Goal: Uniform, readable guard that doesn't require every view to reimplement `test_func`.
- Steps:
  1. Add `MaintainerAccessRequiredMixin` to `core/mixins.py` that encapsulates the existing rule (for now, still `is_staff` or superuser) and handles the 403 response.
  2. Replace per-view `test_func` implementations and manual `if not user.is_staff` checks with the mixin.
  3. Update tests to assert the mixin-based access behavior (still using `is_staff`), ensuring no regressions.
  4. Deploy to production and verify no access regressions.
- Rationale: Reduces duplication, clarifies intent (the "test" name is confusing), and concentrates the rule in one place for a safer future change. Sets up layering later (e.g., more specific mixins like `CanManageMachinesMixin`) without touching every view.

### Phase 2 — Switch to permissions/groups (allow non-staff maintainers)
- Define role
  - Create a "Maintainers" group and custom permission `accounts.can_access_maintainer_portal` on the `Maintainer` model.
  - Seed group and permission via data migration; add all existing maintainers to the group.
- Access checks
  - Update `MaintainerAccessRequiredMixin` to use `user.has_perm('accounts.can_access_maintainer_portal')`. Django's `has_perm()` automatically returns `True` for superusers.
  - Keep view code unchanged beyond the mixin update.
- User lifecycle
  - Registration/invitation/shared-terminal flows: create `Maintainer` profile, assign to Maintainers group; stop setting `is_staff` for new maintainers.
  - `is_superuser` unchanged.
- Discord integration
  - No changes needed. Discord already links by matching usernames to `Maintainer` profiles, with no `is_staff` dependency.
- Data cleanup
  - After Phase 2 is stable, manually remove `is_staff=True` from maintainer accounts that don't need Django admin access (via Django admin or management command).
- Tests and fixtures
  - Update `core/test_utils.py` helpers (`create_staff_user()`, etc.) to create maintainer users via group assignment instead of `is_staff`.
  - Adjust tests that assert `is_staff` to assert maintainer permission/group and access behavior.
- Rollout checks
  - Verify maintainer flows (web + Discord) work for non-staff maintainers.
  - Verify admin access still works for superusers.
