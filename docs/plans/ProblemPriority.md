# Problem Report Prioritization

We want to be able to assign a priority to a Problem Report.

Status: IMPLEMENTED.

## Rationale

Flipfix currently has the following types of records:

- **Problems**, which were originally meant to be reports about playable machines that have an issue. The theory was that we want to be very aware of things that would give visitors a bad experience, and fix them as soon as possible.
- **Log Entries**, which are a record of things done that we write to help future techs, including ourselves.
- **Parts Requests** & updates on them

None of these seem quite right for some of the things it turns out we want to track.

- In the game room
  - Something on a machine that would be nice to do as opposed to an urgent Problem, such as replace a burned-out GI bulb
  - Something on a machine that we should think about doing, such as whether to replace the LEDs on RfM with original bulbs
  - Something on a machine that should be done regularly, such as clean the glass, clean the playfield, play the game and verify it's in good order
- In the workshop
  - Something on a machine that's broken we want to fix later
  - Something on a machine that we want to remember to do later, such as clean the playfield, replace the lock
  - Something on a machine that we want to check before we declare it good, such as do the balls need to be replaced

Our current ways of dealing with these are not adequate. We either:

- Keep these in log entries, which we have to remember to check
- Keep these in problems, which can make it hard to find the urgent visitor-relevant stuff
- Keep these in our conversations and memories, which can be fallible

## Rejected Alternative: a New Tasks Table

Many of the above scenarios are not "problems", but "tasks". They represent future work. We considered creating a Task table, separate from Problem. But we think Problem and Task are too semantically close to separate them in the domain model. For example:

- As a maintainer, I notice something critically broken on a machine in the workshop. It's urgent for that machine, but not urgent compared to the work on machines in the game room. Do I create a Problem or a Task?
- As a maintainer, I notice something that really should be done on a machine in the game room, but isn't an actual problem, it doesn't impede play, like the glass is kind of dirty. Do I create a Problem or a Task?
- As a maintainer, I notice something on a machine that we should think about doing, such as whether to replace the LEDs on RfM with original bulbs. Is that a Task or a Problem?

You see, the categorization gets fuzzy.

- We probably want shades of categories, like big problems vs small problems.
- People wil be flipping the category on an item back and forth. If we model Task and Problem as separate objects, it's kind of a big deal to re-categorize that item. We want all problems and tasks to be a single object, a single table.

## Accepted: Give Problem Reports a Priority

This allows us to create as many shades of meaning as we want, without having to migrate a record between different tables when someone changes its category.

## Should We Rename Problem Report to Task?

There's an argument to be made that we should rename `Problem Report` to `Task`, because every problem is kind of a task, but not every task is a problem. But that'd be super invasive, and it's not a clear slam dunk because lots of things _are_ more clearly problems than tasks.

So maybe we'll do this in the future, but not in V1. First let's add priority to PRoblem Report, see how it works, then evaluate whether to rename to Tasks.

## The Priorities

The list of priorities are something like:

- **Untriaged**
  - Visitors submitting via the public QR code-accessible Submit Problem Report page do not get to set a priority. Instead, a maintainer needs to decide how bad it is. We need some sort of 'untriaged' or 'unknown' state.
  - Maintainers shall not be able to set a Problem Report to Untriaged.
- **Unplayable**
  - Machine is not playable
- **Major**
- **Minor**
  - The default status
- **Task**

The above order is the order they should be displayed in in any list.

## Migration of Existing Problem Reports

Existing Problem Reports in the system should have their priority set to the default, Minor.

## UI

### Global Problem Reports Page

The global Problem Report page at https://flipfix.theflip.museum/problem-reports/ is intended to be a glance-able list of all the urgent, high priority work.

> For example, a maintainer entered a little thing that we won't get to for a while as a Problem Report. William, the museum owner, had the urge to tell him not to, because it will clutter up the global Problem Reports page. But tracking the issue was correct; we just want to sort it low on the "things to do" ranking.

The Problem Report page should list _all_ problems and tasks. Sorting:

- First sorted by open/closed
- Within open, first sort by priority. Within priority, sort by location (floor first, then workshop). Within location, sort by timestamp (newest first).
- Within closed, sorted by timestamp (newest first). No sort by priority or location.

### Problem Report Create Page

On the Problem Report create page ( `/problem-reports/new/` ):

- The priority shall be a dropdown field below Description and above Add Media.

### Problem Report Detail Page

On the Problem Report detail page ( `/problem-reports/<ID>/` ):

- The priority shall be a pill that is settable, similar to a Machine's Status and Location.
- At the same time, make the Open/Closed pill settable, similar to a Machine's Status and Location.
- In the desktop sidebar, it goes to the right of the Open/Closed pill
- On mobile, it goes to the right of the Open/Closed pill. Remove the Close Problem button on mobile, but leave it in the desktop sidebar, on desktop there will be two ways of closing a problem report.

## Notifications

Changing a Problem Report's priority via the pill shall:

- NOT create a Log Entry
- NOT post to Discord

## Wall Display

There is a wall display in the museum. When maintainers come in looking for something to work on, that's what they look at. Somebody comes in, looks at the board, and finds something they're comfortable doing. We want them to bias their choice toward game room issues based on player impact. And if they want to stay in the workshop, then we put them on the most urgent things in the workshop.

This display is currently showing the global Problem Reports page ( /problem-reports/ ). Instead, we want a different page:

- Make it compact enough so that people can scan a reasonable number of problems, such as:
  - Lose the navigation
  - Replace the images with something like "3 images"
- Split into columns by location: floor vs workshop
- Untriaged on top, followed by everything in priority order

This display is currently a 1080p screen, in portrait mode, but it could be rotated it if that makes more sense.

We will a link to this page to the Admin nav items.

Let's do this as a separate commit, separate PR. Don't make a full plan for this part just yet; just be aware of it.
