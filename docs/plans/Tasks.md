# Tasks

Flipfix currently has the following types of records:

- **Problems**, which were meant to be reports about playable machines that have an issue. The theory was that we want to be very aware of things that would give visitors a bad experience, and fix them as soon as possible.
- **Log Entries**, which are a record of things done that we write to help future techs, including ourselves.
- **Parts Requests** & updates on them

None of these seem quite right for some of the other things we want to track.

- In the workshop
  - something on a machine that's broken we want to fix
  - something on a machine that we want to remember to do later, such as clean the playfield, replace the lock
  - something on a machine that we want to check before we declare it good, such as do the balls need to be replaced
- In the game room
  - something on a machine that would be nice to do as opposed to an urgent Problem, such as replace a burned-out GI bulb
  - something on a machine that should be done regularly, such as clean the glass, clean the playfield, play the game and verify it's in good order
  - something on a machine that we should think about, such as whether to replace the LEDs on RfM with original bulbs

Our current ways of dealing with these are not adequate. We either:

- Keep these in log entries, which we have to remember to check
- Keep these in problems, which can make it hard to find the urgent visitor-relevant stuff
- Keep these in our conversations and memories, which can be fallible

## Potential Solutions

There's no concept for "something we should do" that isn't an urgent visitor-facing problem. We could introduce the concept in multiple ways:

- **Task is a new thing**: Task is a new top-level concept that sits along Problem and Parts Request. You can log Task Updates against them.
- **Rename Problem to Task**: Rename Problem to Task, give Task a priority/severity.

An evaluation of each solution:

### Task is a new thing

Are Problem and Task too semantically close to separate them in the domain model? Thought experiments:

- As a maintainer, I notice something critically broken on a machine in the workshop. Do I create a Problem or a Task?
- As a maintainer, I notice something that really should be done on a machine in the game room, like the glass is pretty dirty. Do I create a Problem or a Task?

### Rename Problem to Task

- As a maintainer, I notice something critically broken on a machine in the workshop.
  - I create a Task.
  - In the global list of tasks, we sort machines in the game room above machines elsewhere
  - Maybe I also set the priority to medium? Dunno, feels high is appropriate here.
- As a maintainer, I notice something that really should be done on a machine in the game room, like the glass is pretty dirty.
  - I create a Task. I set the priority = medium (the default is high).

The main issue with this is naming. Problem feels right for visitor-submitted problems and other urgent problems. Task feels right for non-urgent things. What about words like:

- Work Item
- Ticket
- Issue

### Key maintainer start-of-day experiences

These are some key experiences for maintainers walking in the door, wanting to volunteer:

#### Experience: big problems on the floor

There will be a big screen up on the wall of the workshop or game floor, with all the customer-submitted problems. These are the urgent things to look at. So we need a view that only shows problems with machines that are on the floor.

#### Experience: someone comes in and asks "what can I do"

They need to be able to see open problems and todos across all machines.

#### Experience: someone wants to come in do some maintenance on a specific machine

They need to be able to see open problems and todos on that machine.
