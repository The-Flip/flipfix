# Authorization

Flipfix supports the following tiers of users:

| Type of User    | Description                                                                                       |
| --------------- | ------------------------------------------------------------------------------------------------- |
| **Public**      | Unauthenticated guest access.                                                                     |
| **Maintainers** | People with write access. They can create and edit log entries, parts requests, wiki pages etc.   |
| **Superusers**  | Django superusers. Aka admins. They have access to Django admin and a few other admin-only views. |

## How It Works

### Route annotations

Access is specified in routes, rather than (say) an authorization mixin on views. Routes in `flipfix/urls.py` use `flipfix.apps.core.routing.path()` with an `access=` parameter:

```python
from flipfix.apps.core.routing import path

# Default: logged-in maintainer
path("parts/", PartRequestListView.as_view(), name="part-request-list"),

# Public when toggle is on
path("machines/", MachineListView.as_view(), name="maintainer-machine-list", access="public"),

# Always open — infrastructure
path("healthz", healthz, name="healthz", access="always_public"),

# Logged-in, any role
path("profile/", ProfileUpdateView.as_view(), name="profile", access="authenticated"),

# Superuser only
path("terminals/", TerminalListView.as_view(), name="terminal-list", access="superuser"),
```

| Level         | `access=`         | Who                            | Mechanism                                                |
| ------------- | ----------------- | ------------------------------ | -------------------------------------------------------- |
| Always public | `"always_public"` | Anyone, regardless of toggle   | `login_not_required` on the view                         |
| Public        | `"public"`        | Unauthenticated when toggle on | Wrapper enforces toggle + read-only, adds cache headers  |
| Authenticated | `"authenticated"` | Any logged-in user             | Skips maintainer permission check (profile, password)    |
| Maintainer    | `None` (default)  | Logged-in + portal permission  | `LoginRequiredMiddleware` + `MaintainerAccessMiddleware` |
| Superuser     | `"superuser"`     | Superuser only                 | Wrapper raises `PermissionDenied` for non-superusers     |

## Guest behavior

On pages that are read-write for maintainers, here's how they change to read-only for the public:

| Concern                   | Maintainer           | Public                              |
| ------------------------- | -------------------- | ----------------------------------- |
| Settable (dropdown) pills | Interactive dropdown | Static read-only pill               |
| Reporter/maintainer names | Shown                | Hidden (timestamp only)             |
| Edit/action buttons       | Shown                | Hidden                              |
| Navigation                | Full nav + admin     | Filtered to public pages + "Log in" |
| Cache-Control             | None                 | `public, max-age=300`               |
| HTTP methods              | All                  | GET, HEAD, OPTIONS only             |

## Public access toggle

The Constance config value `PUBLIC_ACCESS_ENABLED` (default: `False`) controls `public` access globally. When off, all `access="public"` routes redirect to login. When on, unauthenticated visitors see read-only versions of those pages.

## Middleware stack

1. **`LoginRequiredMiddleware`** (Django 5.1) — redirects unauthenticated users to login unless the view has `login_not_required` set (our `path()` does this for `"always_public"` and `"public"` routes).
2. **`MaintainerAccessMiddleware`** — checks the `can_access_maintainer_portal` permission. Skips views marked `login_not_required` (including `"public"` routes — guests and authenticated non-maintainers see read-only content; authenticated maintainers get full access).

## Detecting guest state in templates

In templates, use `{% if user.is_authenticated %}` to show maintainer-only elements and `{% if not user.is_authenticated %}` for guest-only elements.

**Known limitation:** Template guards use `user.is_authenticated`, not the `can_access_maintainer_portal` permission. An authenticated user without the maintainer permission (an unusual state — all registered users get the permission) would see some interactive UI elements (settable pill dropdowns, reporter names) that maintainers see. This is acceptable because authenticated non-maintainers are not a supported user tier. If a non-maintainer tier is ever added, these guards would need to be revisited.

## Writing guest-aware templates

### Template tags handle it automatically

Most guest awareness is built into template tags — you don't need `{% if not user.is_authenticated %}` blocks for these:

- **Settable pills** (`settable_problem_status_pill`, `settable_machine_status_pill`, etc.) — render static pills for guests
- **Meta formatters** (`problem_report_meta`, `log_entry_meta`, `part_request_meta`, `part_update_meta`) — hide names for guests
- **Navigation** (`desktop_nav`, `mobile_priority_bar`, etc.) — filter items to public-visible pages for guests
- **Report Problem button** (`report_problem_button`) — routes guests to the public QR form, maintainers to the full form

### When you do need `{% if user.is_authenticated %}`

Use guards for interactive elements that aren't encapsulated in a tag:

- Edit/action buttons
- Form submission areas (e.g., "Add Update" button)
- Interactive JavaScript (settable_pill.js, media_grid.js, markdown inline edit)

Shared editable includes (`text_card_editable.html`, `media_card_editable.html`) already have internal guards — no wrapping needed in the calling template.

The `history_link.html` component self-guards with `{% if user.is_superuser %}` — no extra wrapper needed.

## OAuth2/OIDC Provider (SSO)

FlipFix acts as an OAuth2/OIDC authorization server for other apps in the theflip.museum domain. External apps authenticate users via FlipFix — users log in once and get seamless SSO across all apps.

### How SSO works

1. User visits an external app (e.g., `juice.theflip.museum`)
2. The app redirects to `flipfix.theflip.museum/oauth/authorize/` with standard OAuth2 parameters
3. If the user has an active FlipFix session: the authorize endpoint redirects back immediately with an auth code (no login form, no consent screen)
4. If not: FlipFix shows the login page, then completes the flow silently
5. The external app exchanges the code for tokens and calls `/oauth/userinfo/` for identity and capabilities

### Endpoints

| Route                              | Access          | Purpose                                   |
| ---------------------------------- | --------------- | ----------------------------------------- |
| `oauth/authorize/`                 | `authenticated` | OAuth2 authorization (any logged-in user) |
| `oauth/token/`                     | `always_public` | Token exchange (external app, no session) |
| `oauth/revoke/`                    | `always_public` | Token revocation                          |
| `oauth/userinfo/`                  | `always_public` | OIDC UserInfo (Bearer token auth)         |
| `.well-known/openid-configuration` | `always_public` | OIDC discovery                            |
| `.well-known/jwks.json`            | `always_public` | Public signing keys                       |

### Scopes and claims

| Scope          | Claims                                                                     |
| -------------- | -------------------------------------------------------------------------- |
| `openid`       | `sub` (user ID)                                                            |
| `profile`      | `preferred_username`, `name`, `given_name`, `family_name`, `is_maintainer` |
| `email`        | `email`, `email_verified`                                                  |
| `capabilities` | `https://flipfix.theflip.museum/capabilities` (list of capability slugs)   |

### App capabilities

Capabilities are per-app permissions managed by superusers in Django admin. Unlike Django permissions (which control what users can do inside FlipFix), capabilities control what users can do in external apps that authenticate via FlipFix.

- **`AppCapability`** — defines a capability an app supports (e.g., "Control Machine Power" for Juice)
- **`AppCapabilityGrant`** — grants a capability to a user

Superusers manage capabilities via Django admin at `/admin/oauth/`.

### Registering a new client app

1. Create an Application in Django admin (`/admin/oauth2_provider/application/`)
2. Set client type to "Confidential", grant type to "Authorization code"
3. Set `skip_authorization = True` for first-party apps (enables silent SSO)
4. Set the algorithm to RS256
5. Add redirect URIs for the app
6. Create `AppCapability` records for the app's capabilities
7. Grant capabilities to users via `AppCapabilityGrant`

### Configuration

- **`OIDC_RSA_PRIVATE_KEY`** env var: RSA private key (PEM) for signing OIDC tokens
- **`SITE_URL`** env var: Used as the OIDC issuer URL
- Dev settings allow HTTP redirect URIs; prod requires HTTPS

## Making a page public

To make an existing maintainer page publicly accessible:

1. Add `access="public"` to its route in `urls.py`
2. Verify any non-encapsulated interactive elements (edit buttons, forms, action links) are wrapped in `{% if user.is_authenticated %}`. Shared partials like `text_card_editable.html`, `media_card_editable.html`, and `history_link.html` already self-guard — no extra wrapping needed.
3. Add `meta_description` to the view's `get_context_data()`
4. That's it — middleware, cache headers, and template tags handle the rest
