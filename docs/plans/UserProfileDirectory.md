# User Directory & Profile Pages

The Flip museum would like Flipfix to have a user directory and user profile pages, both with user-uploadable photos.

## Goals

- Enable museum volunteers and staff -- all in the maintainers group -- to introduce themselves.
- Enable front desk person -- also in the maintainers group - to quickly and easily verify that people claiming to be volunteers really are.

Currently the museum is using a Discord channel for this named #who-is-who. People post a message with their photo.

## Access

- This would be for all users in the Maintainer group. Anybody who is a Maintainer or superadmin can view the directory and profile pages.
- However, we should probably wrap it in an access check like can_view_user_profiles. This gates access to user profiles AND the directory listing page. Migration puts the Maintainers group into it. This should match the can_manage_catalog pattern.
- The front desk person will be a Maintainer.
- The directory should be accessible from the shared terminal accounts -- this will happen by default, since shared terminal accounts are in the Maintainer group. Yes, this means a kiosk could be set up displaying the user directory.

## Routes

- /users: the user directory listing page
- /users/[username]: the profile page
- /profile: the current user edit page, which probably should have been called account/, but we're not changing it now.

## User-provided content

- Users must post their own media items and upload their own bio
  - Bio field:
    - lives at Maintainer.bio
    - field is our standard markdown field, 300 char max
- Media items can be photo or video
- Users can post multiple media items
  - Max 10 media items
- Users can sort their media items.

## Who & What Is Shown In The Directory Listing Page

- Every Maintainer with is_active = true and is not a shared terminal account is automatically shown
- Directory listing shows "First Last (username)" via the existing display_name_with_username tag, first media item in display order, first line of bio. First line uses the condensed display of markdown technique we use elsewhere, such as in card footers: {{ text|truncatechars:N|render_markdown }}
- Each user is displayed as a tile / card.
  - When there's no media, user is still displayed as a tile / card. Show a funky and slightly fuzzy person or monster silhouette, NOT the standard "missing person" silhouette. Have some fun. Vary it randomly per user.
- There's a search that searches by name, username. Filters as you type, same pattern as the machine instance list page at /machines. Don't invent any new patterns.
- The tiles are sorted alphabetical by display_name

## What is Shown On The /users/[username] Page

- All of the directory content, plus the full bio rendered as markdown, plus all the media items
- /users/[username] 404's if user isn't on the directory listing, meaning they must be a Maintainer, is_active=true, not a shared machine.

## Photo Management

- Lives on the existing account management screen at /profile
- Photo management as a new section below the account fields
- It's the exact same UI as on parts etc, except conditionally rendered only if the user would appear in the directory
- Drag and drop ordering exactly as on parts etc
- Support videos because exactly as on parts etc

## Things We Aren't Doing

### No Moderation

Media and text are live immediately. No facility for flagging objectionable content.

### No Front Desk Functionality

We're doing nothing special for the front desk. No special read-only role.

### No New User Functionality

New users are also not prompted to add photos.

### No Migration

There's no migration:

- All Maintainers automatically appear in it, by virtue of being a maintainer that's not a shared terminal account, with is_active true.
- We don't prompt existing users to add photos.
- We aren't backfilling from Discord

### No delete user account on request

That's a larger system concern, not a user profile feature. For now we can simply take them out of the Maintainer group or mark them as is_active = false.

## Deferred

Things we aren't doing in v1.

### Hyperlinking usernames to their profile

Everywhere on the site we currently display the username, we could hyperlink to this profile. Probably will, but not in V1.

## Implementation Notes

### Relationship to existing media system

We want to reuse the existing media system, which we hope will get us most of the backend and frontend for free:

- Use the existing abstract media-attachment base
- Frontend MultiFileField are already in use in parts/maintenance — reuse those patterns, abstract even more shared code if possible.
- Sounds like drag/drop is not part of the generic system yet. Design it as a generic media-reorder endpoint so that parts/maintenance can adopt it later (they will not adopt it this PR). Consider using whatever reordering functionality we can from the wiki.

If we can reuse MORE of the media system by changing this spec, we should.

### Reusable profile logic

We use the following check multiple places:

```python
is_active=True AND in Maintainers group AND not maintainer.is_shared_account
```

Extract it into a single helper (e.g. is_in_user_directory(user) in core/mixins.py, plus a matching template tag) and use it in all the places.
