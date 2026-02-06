# Wiki

Status: IMPLEMENTED.

## Overview

The museum would like to have a maintenance wiki. It'll have pages like:

- **New Machine Intake**. A checklist of things to do when a new machine comes in. See [NewMachineIntakeChecklist.md](NewMachineIntakeChecklist.md)
- **How to change lights**

## Who are the users?

- **Maintainers on the floor** - need quick answers while standing at a machine, phone in hand
- **New maintainers** - learning procedures, need guidance and checklists
- **Experienced maintainers** - documenting knowledge so it doesn't live only in their heads
- **Museum management** - standardizing procedures, ensuring consistency

## Core use cases

- "How do I do X?" - Quick lookup while working on a machine
- "Walk me through Y" - Step-by-step guidance for multi-step procedures
- "What should I check for Z?" - Checklists and inspection guides
- "Let me document what I learned" - Capturing institutional knowledge

## Location

- URL path: https://flipfix.theflip.museum/wiki/
- This is a new Django app. Django app name: apps/wiki/

## Authorization

Any maintainer can view pages. Any maintainer can author pages.

There is no concept of a 'gardener' or 'moderator' that has more elevated perms. I'm thinking that any sensitive tasks, like system maintenance tasks, are probably superuser tasks, but let's address each of those individually as they come up.

To make this flexible in the future, we could consider having wiki-specific roles, but it's probably YAGNI.

## Editing experience

WYSIWYG is not a hard requirement. Since maintainers already use markdown, maybe markdown is actually the right experience. If whatever module we use has WYSIWYG, I'm not going to turn it off.

## Media support

If it doesn't add too much complexity, authors should be able to upload images and, if not too complex, videos.

Can we re-use the video processing we already have?

## Search

The wiki needs to be full-text searchable.

If someone searches and nothing exists, there need not be a "create this page" feature - it's okay if they have to click a button somewhere. But if the wiki system we use has it, sure leave it.

## Mobile first

The wiki needs to be highly usable from phones.

## Audit trail

We need an audit trail. Options:

- The wiki software comes with its own audit trail?
- We already have an audit log module. Wiki page edits, creates, deletes should all be recorded there. Each wiki page should have the same little history icon that sends admins to the audit log.

## Integration of FlipFix with wiki

We want to integrate the wiki with FlipFix in various ways.

### Links from markdown to wiki

When authoring markdown content in any type of Flipfix record (Problem Report, Log Entry, Part Request, Part Request Update), you should be able to easily link to any wiki page. I'm not sure what it'd look like, but as you type a link, it should autocomplete from the existing wiki pages. Do wiki systems generally support link autocomplete like this?

### Links from wiki to machines

When authoring a wiki page, we want to be able to hyperlink to a machine. I'm not sure what it'd look like, but as you type a link, it should autocomplete from machines names. Do wiki systems generally support link autocomplete like this?

It would hyperlink to the machine's detail page, like /machines/carom/

## Create Record From Wiki

We'd like to be able to take portions of a wiki page and click a button to create a Flipfix record with it.

For example, we should be able to put a big button on the [NewMachineIntakeChecklist.md](NewMachineIntakeChecklist.md) that says something like "Start Intake". When you click it, it opens the Create Problem Report form, prepopulated with the name of that machine and the checklist portion of the page as the Problem Report's Description.

We are considering building a Task entity -- see [Tasks.md](Tasks.md) -- and if we do that, this is more appropriate as a Task than a Problem Report.

See [WikiActionButtons.md](WikiActionButtons.md) for details.

## Machine-specific pages

There will probably be machine-specific wiki pages. However, we're not going to explicitly link them; for example, we won't force the wiki page to be named with the slug of the machine. If we link from the machine detail page to specific wiki pages, we'll somehow configure that on the machine detail page; we'll cross that bridge if/when we decide to build that feature.

## Multi-machine pages

There will probably be wiki pages that apply to multiple machines. For example, Blackout and Gorgar are both System 6 machines and a lot of maintenance is shared between them.

## Wiki page organization

We have not yet figured out all the content that will go in this wiki. I assume the wiki software will have multiple ways of organizing: folders, tags, lists etc. The wiki will grow organically, and I assume different strategies will work best at different stages of the wiki's life. I think the best thing for the moment is to select a highly regarded Wiki CMS module for Django, and trust that it has enough flexibility for our present and future needs.

## Cool future ideas

Interesting ideas, but not for v1:

- **Tag pages with machines**. Allow tagging a page as relevant to particular machine(s). In Flipfix, when creating problem reports, log entries, parts request, surface relevant pages.
- **Cross-references from existing content**. When maintainers write log entries, the system could suggest "This might be worth adding to the wiki" for particularly helpful content

## Navigation

How about navigation is a sidebar (at least on desktop), something like this:

```
Procedures
  New Machine Intake
  Graduating From The Workshop

Machines
  Ballyhoo
    Cleaning
    Replacing Lights
    Where to Get Parts
  Baseball
  Blackout
    System 6 Maintenance ⬅️ included via tag?
  Carom
  Derby Day
  Eight Ball
  Godzilla
  Gorgar
    System 6 Maintenance ⬅️ included via tag?
  ...
```

Note that the `System 6 Maintenance` page must be able to exist multiple places. To me this argues that each of those 'folders' are actually tags. So there's no document named Ballyhoo, if you want an overview document for Ballyhoo you'd go:

```
  Ballyhoo
    Overview
    Cleaning
    Replacing Lights
    Where to Get Parts
```

Note that these are not alphabetical...

So maybe it's more that you build a tree structure, and each folder/tag can hold an ordered list of content?

## Wiki Module Candidates

### Comparison Table

| Feature                                                   | django-wiki                          | django-wakawaka                        | Build your own                    |
| --------------------------------------------------------- | ------------------------------------ | -------------------------------------- | --------------------------------- |
| **License**                                               | ⚠️ GPL-3.0                           | ✅ MIT                                 | ✅ Whatever we want               |
| **Django 5.x support**                                    | ✅ Yes                               | ✅ Yes                                 | ✅ Yes                            |
| **Models**                                                | ✅ Included                          | ✅ Included                            | ❌ Build yourself                 |
| **Views**                                                 | ✅ Included                          | ✅ Included                            | ❌ Build yourself                 |
| **Templates**                                             | ✅ Included (Bootstrap-based)        | ✅ Included                            | ❌ Build yourself                 |
| **Revision history**                                      | ✅ Built-in                          | ✅ Built-in                            | ❌ Leverage audit log             |
| **Revert to previous version**                            | ✅ Built-in                          | ✅ Built-in                            | ❌ Build yourself                 |
| **Diff between versions**                                 | ✅ Built-in                          | ❌ Not built-in                        | ❌ Build yourself                 |
| **Hierarchy**                                             | ✅ Tree structure (django-mptt)      | ⚠️ Via URL paths                       | ❌ Build yourself                 |
| **Tagging/categories**                                    | ❌ Add yourself                      | ❌ Add yourself                        | ❌ Add yourself                   |
| **Page titles with spaces**                               | ✅ Yes                               | ❌ No (slug is the title)              | ❌ Build yourself                 |
| **Auto-linking between pages**                            | ✅ Wiki-style links                  | ✅ CamelCase words become links        | ❌ Build yourself                 |
| **Markdown rendering**                                    | ✅ Built-in                          | ⚠️ Add yourself (use`render_markdown`) | ⚠️ Use existing `render_markdown` |
| **[WYSIWYG editing](#editing-experience)**                | ⚠️ MarkItUp toolbar (not WYSIWYG)    | ❌ Plain textarea                      | ⚠️ Add yourself (e.g., Martor)    |
| **[Full-text search](#search)**                           | ✅ Built-in                          | ❌ Add yourself                        | ❌ Build yourself                 |
| **[Image attachments](#media-support)**                   | ✅ Built-in                          | ⚠️ Via django-attachments package      | ⚠️ Use existing image handling    |
| **[Video attachments](#media-support)**                   | ❌ Add yourself                      | ❌ Add yourself                        | ✅ Use existing video handling    |
| **[Permissions](#authorization)**                         | ✅ Per-article permissions           | ✅ Django's create/edit/delete perms   | ❌ Build yourself                 |
| **[Audit trail](#audit-trail)**                           | ✅ Revision model + logs             | Revision model serves this purpose     | ❌ Leverage audit log             |
| **[Mobile responsive](#mobile-first)**                    | ✅ Bootstrap-based                   | ⚠️ Depends on your template overrides  | ❌ Build yourself                 |
| **Dark mode**                                             | ❌ Not supported                     | ❌ Not supported                       | ✅ Use existing dark mode         |
| **Styling**                                               | ⚠️ Coerce Bootstrap to match Flipfix | ⚠️ Override templates to match Flipfix | ✅ Native Flipfix styling         |
| **[Create Record from Wiki](#create-record-from-wiki)**   | ✅ Easy custom code                  | Custom code on top                     | Custom code, full control         |
| **[Wiki-to-machine links](#links-from-wiki-to-machines)** | Custom code on top                   | Custom code on top                     | Custom code, full control         |
| **Risk of hitting walls**                                 | Low - very full-featured             | Possible if conventions don't fit      | None                              |
| **Plugin ecosystem**                                      | ✅ Has plugin architecture           | ❌ None                                | N/A                               |
| **Community/Support**                                     | Active                               | Minimal                                | N/A                               |
| **Github Stars**                                          | ✅ 1,905                             | ❌ 118                                 | N/A                               |

### Roll Our Own

I'm leaning towards rolling our own. There's been very little innovation in the wiki space in years, and the main contender, `django-wiki` is feeling really old and crufty.

- **Avoid Bootstrap**. Flipfix has highly optimized, tight CSS (doesn't use any CSS frameworks) that works great. I want the wiki to look like part of Flipfix and I don't want to fight bloated Bootstrap to do it.
- **Dark mode**. Flipfix supports dark mode, `django-wiki` does not. I want that support.
- **Avoid GPL**. I want Flipfix to be usable by other open source projects without forcing them into a GPL license. I know practically speaking this enforcement will never happen, I could keep the Apache license and nobody would ever notice... but it still irks.
- **Avoid the MarkItUp toolbar**. `django-wiki`'s editing experience is the MarkItUp toolbar that 1) looks like ass and 2) is so old it uses JQuery. That offends me as a modern, reactive UI developer. Instead, there are more modern packages that support a complete WYSIWYG experience over markdown, if that's what we want.
- **First class integration**. As time goes on, we'll want to integrate the wiki functionality more and more into Flipfix. `django-wiki`'s plugin architecture does make this possible, but I have a nagging feeling that I'll spend more time writing plugins than if we had just built the thing we wanted in the first place. For example, we'd like to tag a page as relevant to particular machine(s)... but `django-wiki` doesn't support tags!
- **Video support**. `django-wiki` doesn't support video. We already implemented video support in Flipfix, I think we can build it easily if we don't have to fight how `django-wiki` thinks.

If we didn't already have extensive experience with `render_markdown`, I wouldn't want to attempt this, but we already use it and it works well.

## Roll Our Own - Architecture

This architecture borrows a lot of thinking from AmpleNote.

The navigation will be tag-based. A document can live in multiple places (aka it's tagging, not folders), and tags can be nested. For example, a document named "System 6 Maintenance" can be tagged `machines/blackout` and `machines/gorgar`, so that it shows up in two tags at `machines/blackout/system-6-maintenance` and `machines/gorgar/system-6-maintenance`.

The document's name and the tags are stored separately. The full unique path is constructed from `{tag}/{page_slug}`.

There's no such thing as an empty tag. Deleting the last wiki page tagged `machines/gorgar` makes that tag disappear.

### Data Model

Six tables:

```python
class WikiPage(models.Model):
    """The actual content of a wiki page."""
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+')
    modified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+')


class WikiPageTag(models.Model):
    """Tags that place a wiki page in the navigation tree. A page can have multiple tags."""
    page = models.ForeignKey(WikiPage, on_delete=models.CASCADE, related_name='tags')
    tag = models.CharField(max_length=500, blank=True)  # e.g., "machines/blackout"; empty string = untagged
    slug = models.SlugField(max_length=200)  # Denormalized from page.slug for uniqueness constraint
    order = models.PositiveIntegerField(null=True, blank=True)  # null = unordered

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['page', 'tag'], name='wikipagetag_unique_page_tag'),
            models.UniqueConstraint(fields=['tag', 'slug'], name='wikipagetag_unique_tag_slug'),
        ]
        ordering = [F('order').asc(nulls_last=True), 'page__title']


class WikiTagOrder(models.Model):
    """Optional explicit ordering for tags in navigation. Tags without entries sort alphabetically."""
    tag = models.CharField(max_length=500, unique=True)  # e.g., "machines/blackout"
    order = models.PositiveIntegerField()  # Always explicit (records only exist when ordering is set)
```

**Key concepts:**

- **Pages** hold content (title, slug, content). The slug is used in URLs.
- **Tags** are hierarchical paths (e.g., `machines/blackout`) that place pages in the navigation tree. A page can have multiple tags, appearing in multiple locations. In the UI, tags render as a folder-like tree structure, but there's no separate Folder model - the tree is derived from tag path prefixes.
- **Full path** is constructed as `{tag}/{page_slug}` (e.g., `machines/blackout/system-6-maintenance`). This is used in URLs and wiki links.
- **Tag ordering** is opt-in via `WikiTagOrder`. Tags with explicit order appear first (sorted by order), then unordered tags (sorted alphabetically).
- **Page ordering** within a tag is stored on `WikiPageTag.order`. Pages without explicit order have `null` and sort alphabetically after ordered pages.
- **Untagged pages** are stored with a `WikiPageTag` record where `tag=""` (empty string). This sentinel value means every page has at least one `WikiPageTag`, and the uniqueness constraint covers all cases. In the UI, these pages appear at the root level of navigation, before any tags. Their URL is `/wiki/doc/{slug}`.
- **Slug uniqueness** is enforced per-tag via database constraint. The slug is denormalized onto `WikiPageTag` so the constraint on `['tag', 'slug']` prevents two pages with the same slug under the same tag. This includes untagged pages (where `tag=""`). When a page's slug changes, all its `WikiPageTag.slug` values are updated in the same transaction.
- **Link references** track outgoing links from wiki pages to prevent broken links and enable reverse lookups. See [MarkdownLinks.md](MarkdownLinks.md) for details.

**Example:**

A page with title "System 6 Maintenance" and slug `system-6-maintenance`, living inside two tags:

| WikiPageTag.tag     | slug                   | order |
| ------------------- | ---------------------- | ----- |
| `machines/blackout` | `system-6-maintenance` | 3     |
| `machines/gorgar`   | `system-6-maintenance` | 1     |

This page appears at:

- `machines/blackout/system-6-maintenance` (third in Blackout)
- `machines/gorgar/system-6-maintenance` (first in Gorgar)

**Link autocomplete:**

When typing a wiki link like `[[System`, autocomplete searches constructed full paths (`tag + "/" + slug`):

- `mach` matches `**mach**ines/blackout/overview`
- `over` matches `machines/blackout/**over**view`
- `black` matches `machines/**black**out/overview`

Simple `icontains` on the full path. Users type whatever they remember.

**Search:**

Full-text search uses `icontains` across multiple fields for v1:

```python
from django.db.models import Q

def search_pages(query: str):
    return WikiPage.objects.filter(
        Q(title__icontains=query) |
        Q(slug__icontains=query) |
        Q(content__icontains=query) |
        Q(tags__tag__icontains=query)
    ).distinct()
```

This ensures searching "Blackout" finds all pages in that tag, not just pages mentioning "Blackout" in body text. The `distinct()` prevents duplicate results when a page matches via multiple tags. Can upgrade to PostgreSQL full-text search later if needed.

### Tag Normalization

Tags are slugified for consistency and clean URLs:

- **Lowercase** - `Machines` → `machines`
- **Hyphens for spaces** - `New Machines` → `new-machines`
- **Alphanumeric and hyphens only** - special characters stripped
- **No leading/trailing slashes** - `/machines/` → `machines`
- **No empty segments** - `machines//blackout` is rejected
- **Empty tag reserved** - users cannot enter `""` as a tag; it's used internally as the sentinel for untagged pages
- **Each segment individually slugified** - `New Machines/Black Out` → `new-machines/black-out`

**Storage:** Tags stored as slugified paths (e.g., `machines/blackout`).

**Display:** Hyphens replaced with spaces, CSS `text-transform: capitalize` handles casing. `machines/blackout` → "Machines / Blackout". Edge cases like acronyms ("api" → "Api" not "API") are accepted limitations.

**User input:** Auto-slugified on save. User types "New Machines/Blackout", stored as `new-machines/blackout`.

### Tag Operations

Since tags are implicit, tag operations are bulk updates to `WikiPageTag.tag` values.

**Rename tag:**

Renaming `machines/blackout` to `machines/black-out` updates all tags that start with the old path:

```python
def rename_tag(old_tag: str, new_tag: str):
    # Reject if new tag or any of its children already exist
    # Uses Q() to check exact match OR child prefix (with trailing slash)
    # This avoids false positives: renaming to "machines/black" is allowed
    # even if "machines/blackout2" exists (different tag, not a collision)
    if WikiPageTag.objects.filter(
        Q(tag=new_tag) | Q(tag__startswith=new_tag + '/')
    ).exists():
        raise ValueError(f"Cannot rename: '{new_tag}' already exists")

    with transaction.atomic():
        # Update WikiPageTag records (exact match + children only, not unrelated prefixes)
        page_tags = list(WikiPageTag.objects.filter(
            Q(tag=old_tag) | Q(tag__startswith=old_tag + '/')
        ))
        for pt in page_tags:
            pt.tag = new_tag + pt.tag[len(old_tag):]
        WikiPageTag.objects.bulk_update(page_tags, ['tag'])

        # Update WikiTagOrder records
        orders = list(WikiTagOrder.objects.filter(
            Q(tag=old_tag) | Q(tag__startswith=old_tag + '/')
        ))
        for order in orders:
            order.tag = new_tag + order.tag[len(old_tag):]
        WikiTagOrder.objects.bulk_update(orders, ['tag'])
```

This handles nested tags automatically: renaming `machines` also updates `machines/blackout`, `machines/gorgar`, etc.

**Delete tag:**

Deleting a tag removes the tag from all pages. Pages that have other tags remain in those locations. Pages with only that tag become **untagged** (moved to root level, accessible at `/wiki/doc/{slug}`).

This maintains the invariant that every page has at least one WikiPageTag.

```python
def delete_tag(tag: str) -> tuple[bool, list[WikiPage], list[WikiPage]]:
    """Delete a tag. Returns (success, blocking_pages, newly_untagged_pages)."""
    page_tags_to_delete = WikiPageTag.objects.filter(
        Q(tag=tag) | Q(tag__startswith=tag + '/')
    )

    # Check for incoming references that would block deletion
    blocking_pages = list(
        WikiPage.objects.filter(
            outgoing_page_links__target__in=page_tags_to_delete
        ).distinct().order_by('title')
    )
    if blocking_pages:
        return (False, blocking_pages, [])

    # Find pages that will become orphaned (only have tags we're deleting)
    pages_in_tag = WikiPage.objects.filter(tags__in=page_tags_to_delete).distinct()
    will_be_orphaned = [
        p for p in pages_in_tag
        if not p.tags.exclude(pk__in=page_tags_to_delete).exists()
    ]

    with transaction.atomic():
        page_tags_to_delete.delete()
        WikiTagOrder.objects.filter(Q(tag=tag) | Q(tag__startswith=tag + '/')).delete()

        # Create untagged records for orphaned pages
        for page in will_be_orphaned:
            WikiPageTag.objects.create(page=page, tag="", slug=page.slug)

    return (True, [], will_be_orphaned)
```

**UX:** Inform the user when pages will be moved to root level:

> **Deleting tag "machines/gorgar"** will affect 5 pages:
>
> - 3 pages have other tags (will remain in navigation)
> - 2 pages will become untagged (moved to root level)

### Page Slug Rename

Because `WikiPageTag.slug` is denormalized from `WikiPage.slug`, the sync is enforced in `WikiPage.save()`. This protects against admin panel edits and shell operations that use `.save()`.

**Warning:** `save()` does NOT run for `QuerySet.update()`, `bulk_update()`, or raw SQL. Never use these to modify `WikiPage.slug`. Migrations that change slugs must update both `WikiPage.slug` and `WikiPageTag.slug` in the same operation.

```python
class WikiPage(models.Model):
    # ... fields ...

    def save(self, *args, **kwargs):
        # Detect slug change
        if self.pk:
            old_slug = WikiPage.objects.filter(pk=self.pk).values_list('slug', flat=True).first()
            slug_changed = old_slug and old_slug != self.slug
        else:
            slug_changed = False

        if slug_changed:
            # Check for collisions in ALL tags this page appears in
            page_tags = self.tags.values_list('tag', flat=True)
            collision = WikiPageTag.objects.filter(
                tag__in=page_tags,
                slug=self.slug
            ).exclude(page=self).exists()

            if collision:
                raise ValidationError(f"Slug '{self.slug}' already exists in one of this page's tags")

        with transaction.atomic():
            super().save(*args, **kwargs)
            if slug_changed:
                self.tags.update(slug=self.slug)
```

**Key points:**

- Sync happens in `save()`, so any code path that saves the page triggers it
- Collision check covers ALL tags, not just one
- Single transaction ensures atomicity
- New pages (no pk yet) skip the slug change check — their `WikiPageTag` records are created separately with the correct slug

### Revision History

`WikiPage` uses django-simple-history (`HistoricalRecords`), consistent with other Flipfix models. This provides full content snapshots on every save, enabling view/diff/revert.

```python
from simple_history.models import HistoricalRecords

class WikiPage(models.Model):
    # ... fields ...
    history = HistoricalRecords()
```

**V1:** No new UI. Superadmins use the existing django-simple-history admin interface for history viewing, diffing, and reverting.

**Future:** Could add maintainer-facing history UI (view revisions, diff, revert) since the `HistoricalRecords` API is just a queryset — no admin required.

### URL Structure

All wiki page content lives under `/wiki/doc/` to separate content from functional routes. This means we don't have reserved keywords that slugs can't use.

**Content URLs:**

- `/wiki/doc/{slug}` - untagged page (e.g., `/wiki/doc/getting-started`)
- `/wiki/doc/{tag}/{slug}` - tagged page (e.g., `/wiki/doc/machines/blackout/system-6-maintenance`)

**URL routing is unambiguous** because slugs cannot contain slashes (enforced by `SlugField`), while tags use slashes as hierarchy separators. This means the last path segment is always the slug:

| URL path after `/wiki/doc/`              | Tag (in DB)         | Slug                   |
| ---------------------------------------- | ------------------- | ---------------------- |
| `overview`                               | `""` (empty string) | `overview`             |
| `machines/overview`                      | `machines`          | `overview`             |
| `machines/blackout/system-6-maintenance` | `machines/blackout` | `system-6-maintenance` |

Routing algorithm:

1. Split path by `/`
2. Last segment = slug
3. Everything before = tag (joined by `/`), or untagged if only one segment

No database lookup required to parse the URL structure.

**Functional URLs** (rest of `/wiki/`):

- `/wiki/` - wiki home/index
- `/wiki/search` - search interface
- `/wiki/create` - create new page
- `/wiki/edit/{path}` - edit existing page
- `/wiki/delete/{path}` - delete page (with confirmation)
- `/wiki/tags` - tag management (if needed)

This avoids needing to maintain a reserved words list for slugs/tags. No risk of a page named "search" or "edit" breaking functional routes.

### Navigation Tree Performance

Building the sidebar navigation tree requires only 2 queries regardless of tree depth:

```python
# Query 1: All page-tag relationships with page data
page_tags = WikiPageTag.objects.select_related('page').all()

# Query 2: Tag ordering
tag_orders = {o.tag: o.order for o in WikiTagOrder.objects.all()}

# Build tree in Python from tag strings
tree = build_tree(page_tags, tag_orders)
```

The `tag=""` sentinel means untagged pages are included in the first query — no separate query needed.

Tree-building is O(N) string parsing in Python, which is trivial. For a wiki with 500 pages across 100 tags, this is 2 queries returning ~600 rows total.

### Editing Experience

For v1 we're not doing WYSIWYG. Beyond the bare textbox where you type markdown, we're only going to support:

- **Checkbox list items**. Creating a new checkbox list item on [enter]; already exists in every markdown editor in the system.
- **Link editing**. Link editing as described in [MarkdownLinks.md](MarkdownLinks.md)

### Media Attachments

**Deferred to a future version.** When implemented, will follow the existing `AbstractMedia` pattern used by `LogEntryMedia` and `ProblemReportMedia`, with video transcoding via Django Q.

## Deferred

These are explicitly excluded from v1.

- Media attachments (images, videos)
- Maintainer-facing revision history UI

### Reverse Lookups (Future, not for v1)

Show related wiki documentation on machine/model detail pages.

- Add "Related Docs" section to machine detail page
- Add "Related Docs" section to model detail page
- Query via `machine.wiki_references.select_related('source_page')`

**Milestone:** Machines/models surface relevant wiki documentation.

### Tag Management (Future, not for v1)

Tools for bulk tag operations.

- Tag ordering UI
- Rename tag UI
- Delete tag UI (with orphan handling)

**Milestone:** Maintainers can reorganize the wiki structure.
