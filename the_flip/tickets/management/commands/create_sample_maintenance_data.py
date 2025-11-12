from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import hashlib
from typing import Dict, Iterable, List, Optional

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from tickets.models import LogEntry, MachineInstance, Maintainer, Task


SAMPLE_BATCH_CODE = "sample-maintenance-2025"
SAMPLE_CONTACT_TAG = f"sample-data::{SAMPLE_BATCH_CODE}"


@dataclass
class Reporter:
    kind: str  # 'visitor' or 'maintainer'
    name: Optional[str] = None
    contact: Optional[str] = None


@dataclass
class StoryEvent:
    action: str
    text: str
    roles: List[int]
    delta_days: int = 0
    delta_hours: int = 0
    machine_status: Optional[str] = None


@dataclass
class TaskScenario:
    title: str
    task_type: str
    problem_type: str
    problem_text: str
    participants: List[str]
    reporter: Reporter
    start_offset_days: int
    template: str
    context: Dict[str, str] = field(default_factory=dict)


@dataclass
class MachineScenario:
    machine_name: str
    base_days_ago: int
    tasks: List[TaskScenario]


class Command(BaseCommand):
    help = "Create layered sample maintenance data on top of legacy imports"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete previously created sample tasks before generating new ones",
        )

    def handle(self, *args, **options):
        self.now = timezone.now()
        self.machine_lookup = self._build_machine_lookup()
        self.maintainer_lookup = self._build_maintainer_lookup()

        reporter_names_missing = self._missing_maintainers_from_csv()
        if reporter_names_missing:
            raise CommandError(
                "Missing Maintainer records for: "
                + ", ".join(sorted(reporter_names_missing))
            )

        clear = options.get("clear", False)

        if clear:
            deleted = self._clear_sample_data()
            self.stdout.write(
                self.style.WARNING(f"Deleted {deleted} previously generated tasks")
            )
        else:
            existing = Task.objects.filter(
                reported_by_contact__startswith=SAMPLE_CONTACT_TAG
            ).count()
            if existing:
                self.stdout.write(
                    self.style.WARNING(
                        "Sample maintenance data already exists. "
                        "Re-run with --clear to regenerate."
                    )
                )
                return

        created_tasks = self._generate_sample_data()
        self.stdout.write(
            self.style.SUCCESS(
                f"✓ Created {created_tasks} sample tasks with layered log entries"
            )
        )

    def _build_machine_lookup(self) -> Dict[str, MachineInstance]:
        lookup = {}
        for machine in MachineInstance.objects.all():
            lookup[machine.name.lower()] = machine
        if not lookup:
            raise CommandError(
                "No machines found. Run create_default_machines before this command."
            )
        return lookup

    def _build_maintainer_lookup(self) -> Dict[str, Maintainer]:
        lookup = {}
        for maintainer in Maintainer.objects.select_related("user"):
            keys = {
                maintainer.user.username,
                maintainer.user.first_name,
                maintainer.user.last_name,
                maintainer.nickname,
            }
            for key in keys:
                if key:
                    lookup[key.strip().lower()] = maintainer
        if not lookup:
            raise CommandError(
                "No maintainers found. Run import_legacy_maintainers before this command."
            )
        return lookup

    def _missing_maintainers_from_csv(self) -> List[str]:
        csv_path = os.path.join(
            os.path.dirname(__file__),
            "../../../..",
            "docs/legacy_data/Maintainers.csv",
        )
        if not os.path.exists(csv_path):
            raise CommandError(f"Maintainers CSV not found at {csv_path}")

        missing = []
        with open(csv_path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                first_name = (row.get("First Name") or "").strip()
                username = (row.get("Username") or "").strip()
                key = first_name or username
                if not key:
                    continue
                if key.strip().lower() not in self.maintainer_lookup:
                    missing.append(key.strip())
        return missing

    def _clear_sample_data(self) -> int:
        qs = Task.objects.filter(reported_by_contact__startswith=SAMPLE_CONTACT_TAG)
        count = qs.count()
        qs.delete()
        return count

    def _generate_sample_data(self) -> int:
        created = 0
        for machine_scenario in SCENARIO_DEFINITIONS:
            machine = self._get_machine(machine_scenario.machine_name)
            base_date = self.now - timedelta(days=machine_scenario.base_days_ago)

            for task_data in machine_scenario.tasks:
                task, participants = self._create_task(machine, base_date, task_data)
                created += 1
                self._play_story(task, participants, task_data)
        return created

    def _get_machine(self, name: str) -> MachineInstance:
        machine = self.machine_lookup.get(name.lower())
        if not machine:
            raise CommandError(f'Machine "{name}" not found. Create it first.')
        return machine

    def _get_maintainers(self, names: Iterable[str]) -> List[Maintainer]:
        maintainers = []
        for name in names:
            maintainer = self.maintainer_lookup.get(name.lower())
            if not maintainer:
                raise CommandError(f'Maintainer "{name}" not found in system.')
            maintainers.append(maintainer)
        return maintainers

    def _create_task(
        self, machine: MachineInstance, base_date: datetime, scenario: TaskScenario
    ) -> tuple[Task, List[Maintainer]]:
        participants = self._get_maintainers(scenario.participants)
        reporter_info = scenario.reporter

        task_kwargs = {
            "machine": machine,
            "type": scenario.task_type,
            "problem_type": scenario.problem_type,
            "problem_text": scenario.problem_text,
            "status": Task.STATUS_OPEN,
            "reported_by_contact": SAMPLE_CONTACT_TAG,
        }

        if reporter_info.kind == "visitor":
            task_kwargs["reported_by_name"] = reporter_info.name or ""
            task_kwargs["device_info"] = reporter_info.contact or ""
        elif reporter_info.kind == "maintainer":
            maintainer = self._get_maintainers([reporter_info.name])[0]
            task_kwargs["reported_by_user"] = maintainer.user
        else:
            raise CommandError(f"Unknown reporter kind: {reporter_info.kind}")

        task = Task.objects.create(**task_kwargs)

        start_time = base_date + timedelta(days=scenario.start_offset_days)
        start_time += self._time_jitter(f"{machine.name}-{scenario.title}-task-start")
        if start_time >= self.now:
            start_time = self.now - timedelta(hours=1)
        task.created_at = start_time
        task.save(update_fields=["created_at"])

        return task, participants

    def _play_story(
        self, task: Task, participants: List[Maintainer], scenario: TaskScenario
    ) -> None:
        renderer = STORY_TEMPLATES.get(scenario.template)
        if not renderer:
            raise CommandError(f'Unknown story template "{scenario.template}"')

        events = renderer(participants, scenario.context)
        current_time = task.created_at
        seed_base = f"{task.machine.name}-{scenario.title}"

        for idx, event in enumerate(events):
            current_time += timedelta(
                days=event.delta_days,
                hours=event.delta_hours,
            )
            current_time += self._time_jitter(f"{seed_base}-event-{idx}")
            if current_time >= self.now:
                current_time = self.now - timedelta(minutes=5)

            maintainers = [participants[idx] for idx in event.roles]
            log_entry = self._apply_event(task, event, maintainers)
            if log_entry:
                log_entry.created_at = current_time
                log_entry.save(update_fields=["created_at"])

    def _apply_event(
        self, task: Task, event: StoryEvent, maintainers: List[Maintainer]
    ) -> Optional[LogEntry]:
        text = event.text

        if event.action == "note":
            log_entry = task.add_note(maintainers, text)
        elif event.action == "machine_status":
            log_entry = task.set_machine_status(
                event.machine_status, maintainers, text=text
            )
        elif event.action == "close":
            log_entry = task.set_status(Task.STATUS_CLOSED, maintainers, text=text)
        elif event.action == "reopen":
            log_entry = task.set_status(Task.STATUS_OPEN, maintainers, text=text)
        else:
            raise CommandError(f"Unknown story action: {event.action}")

        return log_entry

    def _time_jitter(self, seed: str) -> timedelta:
        digest = hashlib.sha256(seed.encode("utf-8")).digest()
        minutes = digest[0] % 60
        seconds = digest[1] % 60
        return timedelta(minutes=minutes, seconds=seconds, microseconds=0)

def _event(
    action: str,
    roles: List[int],
    text: str,
    *,
    delta_days: int = 0,
    delta_hours: int = 0,
    machine_status: Optional[str] = None,
) -> StoryEvent:
    return StoryEvent(
        action=action,
        roles=roles,
        text=text,
        delta_days=delta_days,
        delta_hours=delta_hours,
        machine_status=machine_status,
    )


def _statement(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    if text[0].islower():
        text = text[0].upper() + text[1:]
    if not text.endswith("."):
        text += "."
    return text


def template_standard_fix(
    participants: List[Maintainer], context: Dict[str, str]
) -> List[StoryEvent]:
    followup_gap = int(context.get("followup_gap", 18))

    return [
        _event("note", [0], _statement(f"Confirmed {context['symptom']}")),
        _event(
            "machine_status",
            [0],
            _statement(f"Moved the game to the workshop to {context['prep']}"),
            machine_status=MachineInstance.OPERATIONAL_STATUS_FIXING,
        ),
        _event("note", [1], _statement(context["repair"]), delta_days=1),
        _event(
            "machine_status",
            [0, 1],
            _statement(context["result"]),
            machine_status=MachineInstance.OPERATIONAL_STATUS_GOOD,
            delta_days=1,
        ),
        _event(
            "note",
            [min(2, len(participants) - 1)],
            _statement(context["followup"]),
            delta_days=followup_gap,
        ),
    ]


def template_reopen_cycle(
    participants: List[Maintainer], context: Dict[str, str]
) -> List[StoryEvent]:
    reopen_gap = int(context.get("reopen_gap", 32))

    return [
        _event("note", [0], _statement(f"Documented {context['symptom']}")),
        _event(
            "machine_status",
            [0],
            _statement(f"Marked the cabinet as fixing to {context['prep']}"),
            machine_status=MachineInstance.OPERATIONAL_STATUS_FIXING,
        ),
        _event(
            "machine_status",
            [0, 1],
            _statement(context["initial_fix"]),
            machine_status=MachineInstance.OPERATIONAL_STATUS_GOOD,
            delta_days=2,
        ),
        _event(
            "reopen",
            [0],
            _statement(f"Reopened the task after {context['reopen_trigger']}"),
            delta_days=reopen_gap,
        ),
        _event(
            "machine_status",
            [1],
            _statement(context["second_fix"]),
            machine_status=MachineInstance.OPERATIONAL_STATUS_FIXING,
        ),
        _event(
            "machine_status",
            [0, 1],
            _statement(context["final_result"]),
            machine_status=MachineInstance.OPERATIONAL_STATUS_GOOD,
            delta_days=2,
        ),
        _event(
            "note",
            [min(2, len(participants) - 1)],
            _statement(context["followup"]),
            delta_days=7,
        ),
    ]


def template_status_cycle(
    participants: List[Maintainer], context: Dict[str, str]
) -> List[StoryEvent]:
    return [
        _event("note", [1], _statement(f"Noted {context['symptom']}")),
        _event("note", [0], _statement(f"Laid out {context['plan']}"), delta_hours=4),
        _event(
            "close",
            [0],
            _statement(f"Closed the task after {context['close_summary']}"),
            delta_days=1,
        ),
        _event(
            "reopen",
            [2 if len(participants) > 2 else 0],
            _statement(f"Reopened the task because {context['reopen_reason']}"),
            delta_days=14,
        ),
        _event(
            "close",
            [1],
            _statement(f"Closed it again after {context['final_close']}"),
            delta_days=2,
        ),
        _event(
            "note",
            [0],
            _statement(context["followup"]),
            delta_days=10,
        ),
    ]


def template_long_running(
    participants: List[Maintainer], context: Dict[str, str]
) -> List[StoryEvent]:
    return [
        _event("note", [0], _statement(f"Documented {context['symptom']}")),
        _event(
            "machine_status",
            [0],
            _statement(f"Marked the machine fixing to {context['prep']}"),
            machine_status=MachineInstance.OPERATIONAL_STATUS_FIXING,
        ),
        _event(
            "note",
            [1],
            _statement(context["waiting_on"]),
            delta_days=3,
        ),
        _event(
            "note",
            [2 if len(participants) > 2 else 1],
            _statement(context["cleaning"]),
            delta_days=5,
        ),
        _event(
            "note",
            [0],
            _statement(context["still_open"]),
            delta_days=7,
        ),
    ]


def template_breakdown(
    participants: List[Maintainer], context: Dict[str, str]
) -> List[StoryEvent]:
    return [
        _event("note", [0], _statement(f"Found {context['symptom']}")),
        _event(
            "machine_status",
            [0],
            _statement(f"Set the machine to broken because {context['cause']}"),
            machine_status=MachineInstance.OPERATIONAL_STATUS_BROKEN,
        ),
        _event(
            "note",
            [1],
            _statement(context["plan"]),
            delta_days=1,
        ),
        _event(
            "machine_status",
            [1],
            _statement("Moved it to fixing for bench work"),
            machine_status=MachineInstance.OPERATIONAL_STATUS_FIXING,
            delta_days=7,
        ),
        _event(
            "note",
            [2 if len(participants) > 2 else 1],
            _statement(context["bench"]),
            delta_days=2,
        ),
        _event(
            "machine_status",
            [0, 1],
            _statement(context["result"]),
            machine_status=MachineInstance.OPERATIONAL_STATUS_GOOD,
            delta_days=1,
        ),
        _event(
            "note",
            [2 if len(participants) > 2 else 1],
            _statement(context["followup"]),
            delta_days=10,
        ),
    ]


def template_modern_monitor(
    participants: List[Maintainer], context: Dict[str, str]
) -> List[StoryEvent]:
    return [
        _event("note", [0], _statement(f"Noted {context['symptom']}")),
        _event(
            "note",
            [1],
            _statement(context["diagnostic"]),
            delta_hours=6,
        ),
        _event(
            "machine_status",
            [0],
            _statement(f"Marked the game fixing to {context['prep']}"),
            machine_status=MachineInstance.OPERATIONAL_STATUS_FIXING,
            delta_days=1,
        ),
        _event(
            "machine_status",
            [0, 1],
            _statement(context["result"]),
            machine_status=MachineInstance.OPERATIONAL_STATUS_GOOD,
            delta_days=1,
        ),
        _event(
            "note",
            [2 if len(participants) > 2 else 1],
            _statement(context["followup"]),
            delta_days=5,
        ),
    ]


STORY_TEMPLATES = {
    "standard_fix": template_standard_fix,
    "reopen_cycle": template_reopen_cycle,
    "status_cycle": template_status_cycle,
    "long_running": template_long_running,
    "breakdown": template_breakdown,
    "modern_monitor": template_modern_monitor,
}


def visitor_reporter(name: str, contact: str) -> Reporter:
    return Reporter(kind="visitor", name=name, contact=contact)


def maintainer_reporter(name: str) -> Reporter:
    return Reporter(kind="maintainer", name=name)


def task(
    title: str,
    *,
    task_type: str,
    problem_type: str,
    problem_text: str,
    participants: List[str],
    reporter: Reporter,
    start_offset_days: int,
    template: str,
    context: Dict[str, str],
) -> TaskScenario:
    return TaskScenario(
        title=title,
        task_type=task_type,
        problem_type=problem_type,
        problem_text=problem_text,
        participants=participants,
        reporter=reporter,
        start_offset_days=start_offset_days,
        template=template,
        context=context,
    )


def machine_scenario(
    machine_name: str, base_days_ago: int, tasks: List[TaskScenario]
) -> MachineScenario:
    return MachineScenario(machine_name=machine_name, base_days_ago=base_days_ago, tasks=tasks)


SCENARIO_DEFINITIONS: List[MachineScenario] = [
    machine_scenario(
        "Ballyhoo",
        base_days_ago=430,
        tasks=[
            task(
                "Left payout chute hangs",
                task_type=Task.TYPE_PROBLEM_REPORT,
                problem_type=Task.PROBLEM_STUCK_BALL,
                problem_text="Visitor reported the payout ball hanging under the left nail after wins.",
                participants=["William", "Elijah", "Eddie"],
                reporter=visitor_reporter("Free Play Night guest", "freeplay@theflip.com"),
                start_offset_days=0,
                template="reopen_cycle",
                context={
                    "symptom": "the ball wedging under the left payout nail after payouts",
                    "prep": "pull the top arch and burnish the nail heads",
                    "initial_fix": "filed the mushroomed nails and waxed the chute",
                    "reopen_trigger": "humid Saturday crowd made the slide drag again",
                    "second_fix": "added a slim brass shim and polished the lane edges",
                    "final_result": "returned the payout path to a smooth glide and reset it to the floor",
                    "followup": "will monitor humidity notes during the next volunteer night",
                },
            ),
            task(
                "Cabinet legs drift out of level",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Cabinet leans toward the entry wall after visitors lean on it.",
                participants=["William", "Sam", "Luis"],
                reporter=maintainer_reporter("William"),
                start_offset_days=12,
                template="standard_fix",
                context={
                    "symptom": "the front left leg sinking into tired floor shims",
                    "prep": "swap the swollen shims and re-level the cabinet",
                    "repair": "installed new protectors and torqued the carriage bolts",
                    "result": "brought the bubble back to center and tightened locknuts",
                    "followup": "will re-check level after the weekly floor scrub",
                },
            ),
            task(
                "Ball lifter chain slips",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Chain-driven ball lift occasionally loses engagement mid-game.",
                participants=["Elijah", "Ken", "Jerry"],
                reporter=maintainer_reporter("Elijah"),
                start_offset_days=24,
                template="long_running",
                context={
                    "symptom": "the ball lifter chain slipping every few games",
                    "prep": "pull the lift mech to the bench for teardown",
                    "waiting_on": "ordered reproduction chain links and noted the lead time",
                    "cleaning": "Jerry degreased the track while Ken cleaned guides",
                    "still_open": "still waiting on the shipment before reassembling",
                },
            ),
            task(
                "Glass rattles during knock-off",
                task_type=Task.TYPE_PROBLEM_REPORT,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Guests report the glass rattling loudly when the payout knocks.",
                participants=["William", "Eddie", "Luis"],
                reporter=visitor_reporter("Family Day visitor", "familyday@museum.com"),
                start_offset_days=36,
                template="status_cycle",
                context={
                    "symptom": "glass rattling during the knock-off coil fire",
                    "plan": "add felt along the lockdown bar and reseat the glass",
                    "close_summary": "added thin felt strips and snugged the latch",
                    "reopen_reason": "heat from lamps loosened the felt and the rattle came back",
                    "final_close": "shimmed the lockdown receiver and damped the corners",
                    "followup": "scheduled another check during the March tournament night",
                },
            ),
            task(
                "Spring gate tension inconsistent",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Upper spring gate sometimes fires balls back toward shooter lane.",
                participants=["Elijah", "Sam", "John"],
                reporter=maintainer_reporter("Sam"),
                start_offset_days=48,
                template="standard_fix",
                context={
                    "symptom": "upper spring gate tossing balls sideways",
                    "prep": "pull the gate assembly for inspection",
                    "repair": "rebent the spring steel and replaced a fatigued rivet",
                    "result": "brought the gate back to a gentle one-way feed",
                    "followup": "John will spot-check tension during Friday open play",
                },
            ),
            task(
                "Coin door lock replacement",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_NO_CREDITS,
                problem_text="Keyed-alike lock set needs to match the workshop set.",
                participants=["William", "Ken", "Kyle"],
                reporter=maintainer_reporter("Ken"),
                start_offset_days=60,
                template="standard_fix",
                context={
                    "symptom": "coin door lock seized with the old operator key",
                    "prep": "pull the door and clean the coin reject hardware",
                    "repair": "installed the keyed-alike lockset and lubed the mech",
                    "result": "door now opens with the new master keys",
                    "followup": "Kyle will apply matching labels after the next public day",
                },
            ),
            task(
                "Arch artwork touch-up",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Arch art scuffed from repeated arch removals for service.",
                participants=["Sam", "Eddie", "Laura"],
                reporter=maintainer_reporter("Sam"),
                start_offset_days=72,
                template="long_running",
                context={
                    "symptom": "scuffs along the painted arch trim",
                    "prep": "remove the arch and sand the edges smooth",
                    "waiting_on": "mixed color-matched paints and waiting for curing time",
                    "cleaning": "Laura wiped the exposed shooter lane and apron",
                    "still_open": "keeping the arch off the game until the lacquer fully cures",
                },
            ),
            task(
                "Score card rewrite",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Need clearer instructions explaining scoring for tours.",
                participants=["William", "Reba", "Diana"],
                reporter=maintainer_reporter("William"),
                start_offset_days=84,
                template="status_cycle",
                context={
                    "symptom": "tour groups keep asking how the manual scoring works",
                    "plan": "rewrite the card with bigger lettering and color cues",
                    "close_summary": "printed a cleaner card and sealed it under mylar",
                    "reopen_reason": "docent feedback said the payout blurb was still confusing",
                    "final_close": "rephrased the copy and added a simple diagram",
                    "followup": "Diana will proofread again next rotating exhibit day",
                },
            ),
            task(
                "Playfield waxing rotation",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Keep the bagatelle field waxed so balls don't chew the paint.",
                participants=["Elijah", "Luis", "Caleb"],
                reporter=maintainer_reporter("Elijah"),
                start_offset_days=96,
                template="standard_fix",
                context={
                    "symptom": "wax film thinning near the left lanes",
                    "prep": "tape off the arch and clean the field",
                    "repair": "hand-applied fresh wax and buffed high-traffic lanes",
                    "result": "restored a slow, even glide for the balls",
                    "followup": "Caleb logged the next waxing date for June",
                },
            ),
            task(
                "Shooter rod alignment",
                task_type=Task.TYPE_PROBLEM_REPORT,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Shooter feels rough and drags against the housing.",
                participants=["William", "Ken", "Eddie"],
                reporter=visitor_reporter("Pinball League player", "league@theflip.com"),
                start_offset_days=108,
                template="standard_fix",
                context={
                    "symptom": "shooter rod scraping the housing on launch",
                    "prep": "pull the shooter assembly and clean the sleeve",
                    "repair": "polished the rod, replaced the spring, and realigned the housing",
                    "result": "launch now feels smooth and centered",
                    "followup": "Eddie will relube the plunger during monthly cleaning",
                },
            ),
        ],
    ),
    machine_scenario(
        "Carom",
        base_days_ago=400,
        tasks=[
            task(
                "Totalizer window fogging",
                task_type=Task.TYPE_PROBLEM_REPORT,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Visitors can't read the payout totalizer through the fogged window.",
                participants=["Elijah", "William", "Jerry"],
                reporter=visitor_reporter("Weekday docent", "docent@theflip.com"),
                start_offset_days=0,
                template="standard_fix",
                context={
                    "symptom": "condensation building inside the totalizer window",
                    "prep": "pull the backglass panel and dry the channel",
                    "repair": "polished the plex window and added fresh foam tape",
                    "result": "sealed the window so scores stay readable",
                    "followup": "Jerry will monitor it after the next humid spell",
                },
            ),
            task(
                "Payout relay double fires",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Relay that dumps payout cups is double-firing on jackpots.",
                participants=["William", "Ken", "Alex"],
                reporter=maintainer_reporter("William"),
                start_offset_days=10,
                template="breakdown",
                context={
                    "symptom": "payout relay chattering and dumping extra balls",
                    "cause": "a charred coil sleeve and gummy switch stack",
                    "plan": "ordered a new coil and cleaned the switch blades",
                    "bench": "Alex scoped the contacts and verified voltages",
                    "result": "restored crisp single payouts and returned cabinet to floor",
                    "followup": "Ken will re-check the stack tension next service rotation",
                },
            ),
            task(
                "Shooter lane lacquer touch-up",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Shooter lane finish is wearing through from constant play.",
                participants=["Sam", "Luis", "Laura"],
                reporter=maintainer_reporter("Sam"),
                start_offset_days=22,
                template="long_running",
                context={
                    "symptom": "lacquer flaking along the shooter lane groove",
                    "prep": "strip the lane and tape off the stencil",
                    "waiting_on": "waiting on a low-VOC lacquer shipment",
                    "cleaning": "Luis vacuumed the cab while Laura wiped plastics",
                    "still_open": "keeping the lane taped off until the finish cures",
                },
            ),
            task(
                "Coin cup jams",
                task_type=Task.TYPE_PROBLEM_REPORT,
                problem_type=Task.PROBLEM_NO_CREDITS,
                problem_text="Guests report nickels hanging halfway down the payout cup.",
                participants=["Elijah", "Ken", "Eddie"],
                reporter=visitor_reporter("Morning volunteer", "frontdesk@theflip.com"),
                start_offset_days=34,
                template="reopen_cycle",
                context={
                    "symptom": "coins jamming in the payout cup throat",
                    "prep": "pull the throat guides and clean the casting",
                    "initial_fix": "polished the cup and waxed the chute",
                    "reopen_trigger": "a warped dime wedged the cup again during a party rental",
                    "second_fix": "opened the throat slightly and chamfered the edge",
                    "final_result": "payouts drop cleanly even with mixed coin batches",
                    "followup": "Eddie will keep the spare cup handy at the desk",
                },
            ),
            task(
                "Backbox bulbs flicker",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Score bulbs flicker when the motor cycles.",
                participants=["William", "John", "Kyle"],
                reporter=maintainer_reporter("John"),
                start_offset_days=46,
                template="status_cycle",
                context={
                    "symptom": "backbox bulbs flickering whenever the score motor spins",
                    "plan": "clean sockets and tighten ground braid",
                    "close_summary": "burnished the sockets and reflowed a cracked lug",
                    "reopen_reason": "Kyle noticed the flicker return when the motor warmed up",
                    "final_close": "added a new ground jumper and retightened the stack",
                    "followup": "William will watch it during the electro-mechanical tour",
                },
            ),
            task(
                "Leg brace swap",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Rear leg brace cracked near the carriage bolt hole.",
                participants=["Elijah", "Sam", "Luis"],
                reporter=maintainer_reporter("Elijah"),
                start_offset_days=58,
                template="standard_fix",
                context={
                    "symptom": "rear brace cracking and letting the cabinet sway",
                    "prep": "jack up the rear and remove the brace",
                    "repair": "fitted a new hardwood brace and added proper washers",
                    "result": "cabinet stands solid even when visitors lean on it",
                    "followup": "Luis will wipe the legs down after every floor cleaning",
                },
            ),
        ],
    ),
    machine_scenario(
        "Trade Winds",
        base_days_ago=360,
        tasks=[
            task(
                "Score stepper sluggish",
                task_type=Task.TYPE_PROBLEM_REPORT,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Visitors see the score lights lag two steps during play.",
                participants=["William", "Ken", "Sam"],
                reporter=visitor_reporter("Weekend volunteer", "weekend@theflip.com"),
                start_offset_days=0,
                template="standard_fix",
                context={
                    "symptom": "score stepper lagging and occasionally skipping",
                    "prep": "pull the stepper to the bench for teardown",
                    "repair": "cleaned the rivets, rebuilt the springs, and lubed the pawl",
                    "result": "stepper now advances crisply with each hit",
                    "followup": "Sam will log another test game after the next damp morning",
                },
            ),
            task(
                "Flasher sockets corroded",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Backbox flashers intermittent after years of storage.",
                participants=["Ken", "Jerry", "Kyle"],
                reporter=maintainer_reporter("Ken"),
                start_offset_days=12,
                template="breakdown",
                context={
                    "symptom": "flasher sockets arcing and sputtering",
                    "cause": "corroded socket tabs and frayed braid",
                    "plan": "replace the sockets and run fresh ground braid",
                    "bench": "Jerry continuity-tested each string before reinstalling",
                    "result": "flashers pop reliably without flicker",
                    "followup": "Kyle will dust the backbox quarterly so oxidation stays away",
                },
            ),
            task(
                "Conversion wiring audit",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Need to verify wartime conversion wiring before longer runs.",
                participants=["William", "Sam", "John"],
                reporter=maintainer_reporter("William"),
                start_offset_days=24,
                template="long_running",
                context={
                    "symptom": "mystery jumpers from the wartime conversion still unverified",
                    "prep": "trace every jumper against the wartime schematic",
                    "waiting_on": "collecting reference photos from other owners",
                    "cleaning": "John dusted the relay board while Sam bundled wires",
                    "still_open": "keeping the task open until every jumper is documented",
                },
            ),
            task(
                "Warped playfield corner",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Right rear playfield corner lifting from the lockdown pressure.",
                participants=["Ken", "Luis", "Laura"],
                reporter=maintainer_reporter("Ken"),
                start_offset_days=36,
                template="status_cycle",
                context={
                    "symptom": "rear corner bowed up causing balls to drift",
                    "plan": "steam the plywood and clamp it flat",
                    "close_summary": "clamped the corner and reinstalled the trim",
                    "reopen_reason": "after a week the bow returned when the hall heated up",
                    "final_close": "added hidden braces and relieved the lockdown pressure",
                    "followup": "Laura will watch that corner during cleanings",
                },
            ),
            task(
                "Upper kickout weak",
                task_type=Task.TYPE_PROBLEM_REPORT,
                problem_type=Task.PROBLEM_STUCK_BALL,
                problem_text="Kickout saucer can’t clear the ball up to the top lanes.",
                participants=["William", "Sam", "Eddie"],
                reporter=visitor_reporter("High score chaser", "scores@theflip.com"),
                start_offset_days=48,
                template="reopen_cycle",
                context={
                    "symptom": "kickout saucer barely clearing the lip",
                    "prep": "pull the coil and degrease the plunger",
                    "initial_fix": "swapped in a fresh sleeve and stretched the spring",
                    "reopen_trigger": "long games on league night made the coil fade again",
                    "second_fix": "upgraded the coil stop and resurfaced the saucer",
                    "final_result": "kickout now thumps the ball up top every time",
                    "followup": "Eddie logged the coil temp readings for future reference",
                },
            ),
            task(
                "Apron repaint and copy",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Apron paint flaking; need fresh instructional copy.",
                participants=["Sam", "Laura", "Reba"],
                reporter=maintainer_reporter("Sam"),
                start_offset_days=60,
                template="long_running",
                context={
                    "symptom": "apron paint flaking where hands rest",
                    "prep": "strip the apron and sand to bare metal",
                    "waiting_on": "waiting for stencils to dry before spraying color",
                    "cleaning": "Laura polished the shooter gauge and Reba redrafted the copy",
                    "still_open": "holding final clear coat until humidity drops",
                },
            ),
        ],
    ),
    machine_scenario(
        "Baseball",
        base_days_ago=330,
        tasks=[
            task(
                "Pitch motor slipping",
                task_type=Task.TYPE_PROBLEM_REPORT,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Pitch motor sometimes stalls before throwing the ball.",
                participants=["William", "Ken", "Jerry"],
                reporter=visitor_reporter("Birthday rental guest", "rentals@theflip.com"),
                start_offset_days=0,
                template="standard_fix",
                context={
                    "symptom": "pitch motor slipping during wind-up",
                    "prep": "pull the motor board for inspection",
                    "repair": "replaced the belt and dressed the pulley",
                    "result": "pitches now zip downfield without hesitation",
                    "followup": "Jerry will keep the motor housing dusted between rentals",
                },
            ),
            task(
                "Retrofit flipper bushings",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Old retrofit flippers have sloppy bushings.",
                participants=["Alex", "Ben", "Ken"],
                reporter=maintainer_reporter("Alex"),
                start_offset_days=12,
                template="breakdown",
                context={
                    "symptom": "retrofit flippers squeaking and dragging",
                    "cause": "ovalized bushings and tired coil stops",
                    "plan": "install modern bushings and rebuild the stops",
                    "bench": "Ben measured end-of-stroke gap and set proper angles",
                    "result": "flippers feel crisp without buzzing",
                    "followup": "Ken will verify alignment during next rules class",
                },
            ),
            task(
                "Backbox murals streaking",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Backbox lighting streaks the baseball mural after an hour.",
                participants=["William", "Kyle", "Laura"],
                reporter=maintainer_reporter("Laura"),
                start_offset_days=24,
                template="status_cycle",
                context={
                    "symptom": "mural lighting streaks appearing after warm-up",
                    "plan": "diffuse the light and clean the plex",
                    "close_summary": "added vellum diffusers and wiped residue",
                    "reopen_reason": "Kyle saw streaks return during the Saturday clinic",
                    "final_close": "installed LED strips with dimmer control",
                    "followup": "William will watch for hotspots during tours",
                },
            ),
            task(
                "Coin door switch bounce",
                task_type=Task.TYPE_PROBLEM_REPORT,
                problem_type=Task.PROBLEM_NO_CREDITS,
                problem_text="Players have to slam the coin door to add credits.",
                participants=["Ken", "Eddie", "Luis"],
                reporter=visitor_reporter("Arcade club kid", "club@theflip.com"),
                start_offset_days=36,
                template="reopen_cycle",
                context={
                    "symptom": "coin switch bouncing and not registering every drop",
                    "prep": "clean the switch stack and re-gap the leafs",
                    "initial_fix": "polished contacts and replaced the return spring",
                    "reopen_trigger": "door flexed again after a big crowd leaned on it",
                    "second_fix": "added a backing plate and stiffened the door frame",
                    "final_result": "credits register on a light coin drop now",
                    "followup": "Luis will remind volunteers not to lean on the door",
                },
            ),
            task(
                "Spinner target cracked",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Outfield spinner target cracked near the rivet.",
                participants=["Sam", "Ethan", "Laura"],
                reporter=maintainer_reporter("Sam"),
                start_offset_days=48,
                template="long_running",
                context={
                    "symptom": "spinner target cracked and dragging mid-spin",
                    "prep": "remove the spinner assembly for template tracing",
                    "waiting_on": "waiting on a silkscreened replacement",
                    "cleaning": "Ethan polished the wireforms while Laura cleaned plastics",
                    "still_open": "holding installation until the deco dries",
                },
            ),
            task(
                "Score reels gummy",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Tens reel sticks on player two after long games.",
                participants=["William", "Ken", "Ben"],
                reporter=maintainer_reporter("Ken"),
                start_offset_days=60,
                template="standard_fix",
                context={
                    "symptom": "player two tens reel sticking mid-rotation",
                    "prep": "strip the reel and clean the index arm",
                    "repair": "burnished the rivets and replaced the plunger spring",
                    "result": "reel now snaps forward without hesitation",
                    "followup": "Ben will drop conductive lube during monthly service",
                },
            ),
        ],
    ),
    machine_scenario(
        "Derby Day",
        base_days_ago=300,
        tasks=[
            task(
                "Horse race unit timing",
                task_type=Task.TYPE_PROBLEM_REPORT,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Horses stumble because the race unit lags during payouts.",
                participants=["Elijah", "Sam", "Jerry"],
                reporter=visitor_reporter("Racing fan", "derby@theflip.com"),
                start_offset_days=0,
                template="standard_fix",
                context={
                    "symptom": "horse race unit lagging a step behind",
                    "prep": "pull the race assembly for cleaning",
                    "repair": "scrubbed rivets, lubed gears, and reset the pawl tension",
                    "result": "horses advance smoothly with the chime",
                    "followup": "Jerry will recheck timing during the Saturday demo",
                },
            ),
            task(
                "Score motor howl",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Score motor howls whenever the bonus cycles.",
                participants=["William", "Ken", "Mark"],
                reporter=maintainer_reporter("William"),
                start_offset_days=10,
                template="breakdown",
                context={
                    "symptom": "score motor howling through each rotation",
                    "cause": "dried bearings and a glazed cam stack",
                    "plan": "pull the motor, clean cams, and replace bearings",
                    "bench": "Mark repacked the bearings and checked end-play",
                    "result": "motor now spins quietly with crisp indexing",
                    "followup": "Ken will oil the felts every quarter",
                },
            ),
            task(
                "Tilt bob jumpy",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Tilt bob too sensitive for public play.",
                participants=["Elijah", "Luis", "Kyle"],
                reporter=maintainer_reporter("Elijah"),
                start_offset_days=22,
                template="status_cycle",
                context={
                    "symptom": "tilt warnings firing from small bumps",
                    "plan": "clean the bob cup and dial back the gap",
                    "close_summary": "polished the cup and reset the ring spacing",
                    "reopen_reason": "Kyle noticed it drift back after transport",
                    "final_close": "installed a lock nut and added a travel block",
                    "followup": "Luis will verify the spacing during cleaning day",
                },
            ),
            task(
                "Pop bumper caps cracked",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Bumper caps show cracks from UV exposure.",
                participants=["Sam", "Laura", "Reba"],
                reporter=maintainer_reporter("Sam"),
                start_offset_days=34,
                template="long_running",
                context={
                    "symptom": "bumper caps cracked and yellowed",
                    "prep": "pull caps and measure for reproduction",
                    "waiting_on": "waiting for silk-screened replacements",
                    "cleaning": "Laura polished the bumper bodies and Reba archived the art",
                    "still_open": "holding install until the ink cures",
                },
            ),
            task(
                "Start button intermittent",
                task_type=Task.TYPE_PROBLEM_REPORT,
                problem_type=Task.PROBLEM_NO_CREDITS,
                problem_text="Start button sometimes dead until slapped.",
                participants=["William", "Ken", "Eddie"],
                reporter=visitor_reporter("League scorekeeper", "leaguecaptain@theflip.com"),
                start_offset_days=46,
                template="reopen_cycle",
                context={
                    "symptom": "start button leaf switch sticking",
                    "prep": "clean the contacts and tighten the stack screws",
                    "initial_fix": "burnished the contacts and added backing foam",
                    "reopen_trigger": "after tournament play the button stuck again",
                    "second_fix": "replaced the leaf set and added a spacer",
                    "final_result": "button fires immediately every press",
                    "followup": "Eddie logged to recheck before big events",
                },
            ),
            task(
                "Match unit clean-up",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Match unit gummy after storage; needs cleaning.",
                participants=["Elijah", "Sam", "Jerry"],
                reporter=maintainer_reporter("Sam"),
                start_offset_days=58,
                template="standard_fix",
                context={
                    "symptom": "match unit sluggish returning to zero",
                    "prep": "remove the unit and strip the grease",
                    "repair": "soaked the drum, polished the fingers, reapplied light lube",
                    "result": "match snaps to position instantly now",
                    "followup": "Jerry will hit the drum with contact cleaner quarterly",
                },
            ),
        ],
    ),
    machine_scenario(
        "Roto Pool",
        base_days_ago=270,
        tasks=[
            task(
                "Turret alignment drifts",
                task_type=Task.TYPE_PROBLEM_REPORT,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Rotating turret stops between targets after a few games.",
                participants=["William", "Elijah", "Ken"],
                reporter=visitor_reporter("Docent-led tour", "tour@theflip.com"),
                start_offset_days=0,
                template="standard_fix",
                context={
                    "symptom": "turret parking between scoring holes",
                    "prep": "pull the turret and reset the detent",
                    "repair": "cleaned the index wheel and swapped a weak spring",
                    "result": "turret now snaps to each pocket cleanly",
                    "followup": "Ken will verify alignment monthly",
                },
            ),
            task(
                "Bumper scoring wire break",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Right bumper stopped scoring mid-day.",
                participants=["Elijah", "Alex", "Ethan"],
                reporter=maintainer_reporter("Elijah"),
                start_offset_days=12,
                template="breakdown",
                context={
                    "symptom": "right bumper lit but not scoring",
                    "cause": "a brittle cloth wire snapped under the playfield",
                    "plan": "run new cloth wire and add strain relief",
                    "bench": "Alex soldered the harness while Ethan dressed the leads",
                    "result": "bumper now scores and chimes reliably",
                    "followup": "Ethan will inspect all bumper wires during cleaning",
                },
            ),
            task(
                "Turret decals cleaning",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Turret numbers grimy; need careful cleaning.",
                participants=["Sam", "Laura", "Reba"],
                reporter=maintainer_reporter("Sam"),
                start_offset_days=24,
                template="long_running",
                context={
                    "symptom": "turret decals grimy and flaking",
                    "prep": "remove the turret plastics and test solvents",
                    "waiting_on": "waiting on archival decal scans before touch-up",
                    "cleaning": "Laura gently cleaned each insert while Reba photographed art",
                    "still_open": "holding final clear until scans are archived",
                },
            ),
            task(
                "Ball return feed slow",
                task_type=Task.TYPE_PROBLEM_REPORT,
                problem_type=Task.PROBLEM_STUCK_BALL,
                problem_text="Ball return mossy, takes too long between plunges.",
                participants=["William", "Jerry", "Luis"],
                reporter=visitor_reporter("Summer camp kid", "camp@theflip.com"),
                start_offset_days=36,
                template="reopen_cycle",
                context={
                    "symptom": "ball return feed slowing after a few plays",
                    "prep": "clean the trough and wax the guide",
                    "initial_fix": "scrubbed the trough and adjusted the kicker",
                    "reopen_trigger": "dust from the adjacent build-up slowed it again",
                    "second_fix": "lined the trough with fresh mylar and tightened the spring",
                    "final_result": "balls feed quickly even after long sessions",
                    "followup": "Luis will vacuum that corner weekly",
                },
            ),
            task(
                "Carryover lights intermittent",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Carryover inserts flicker if the cabinet shakes.",
                participants=["Elijah", "Alex", "Justin"],
                reporter=maintainer_reporter("Alex"),
                start_offset_days=48,
                template="status_cycle",
                context={
                    "symptom": "carryover insert lights flickering",
                    "plan": "reflow the lamp board and add a ground strap",
                    "close_summary": "reflowed solder puddles and secured the harness",
                    "reopen_reason": "Justin saw them flicker again during cleaning",
                    "final_close": "added a new ground bus and zip-tied the harness",
                    "followup": "Elijah will check again after transport to events",
                },
            ),
            task(
                "Cabinet polish rotation",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Cabinet sides getting dull from constant hands.",
                participants=["Sam", "Luis", "Laura"],
                reporter=maintainer_reporter("Sam"),
                start_offset_days=60,
                template="standard_fix",
                context={
                    "symptom": "cabinet lacquer dull where visitors lean",
                    "prep": "mask the trim and clean the cabinet walls",
                    "repair": "applied fresh polish and buffed the stenciling",
                    "result": "colors pop again without sticky spots",
                    "followup": "Laura scheduled another light polish in six weeks",
                },
            ),
        ],
    ),
    machine_scenario(
        "Teacher's Pet",
        base_days_ago=240,
        tasks=[
            task(
                "Bonus ladder miscounts",
                task_type=Task.TYPE_PROBLEM_REPORT,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Bonus ladder occasionally jumps two steps.",
                participants=["William", "Elijah", "Sam"],
                reporter=visitor_reporter("After-school chaperone", "school@theflip.com"),
                start_offset_days=0,
                template="standard_fix",
                context={
                    "symptom": "bonus ladder occasionally skipping a count",
                    "prep": "pull the bonus unit for cleaning",
                    "repair": "polished the rivets and reset the wiper tension",
                    "result": "ladder now advances one step at a time",
                    "followup": "Sam will monitor counts during Thursday league",
                },
            ),
            task(
                "Drop target bank sticks",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Reset bank hangs halfway up when warm.",
                participants=["Elijah", "Ken", "James"],
                reporter=maintainer_reporter("Ken"),
                start_offset_days=10,
                template="breakdown",
                context={
                    "symptom": "drop target bank hanging mid-reset",
                    "cause": "swollen bakelite links and gummed plungers",
                    "plan": "rebuild the bank with fresh links and springs",
                    "bench": "James sanded the guides and checked coil resistance",
                    "result": "bank now snaps up even after long play",
                    "followup": "Ken will add a light dusting of graphite quarterly",
                },
            ),
            task(
                "Instruction cards refreshed",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Need friendlier cards explaining add-a-ball rules.",
                participants=["William", "Reba", "Diana"],
                reporter=maintainer_reporter("Reba"),
                start_offset_days=20,
                template="status_cycle",
                context={
                    "symptom": "guests confused by add-a-ball text",
                    "plan": "rewrite the cards with clearer copy",
                    "close_summary": "printed new cards and laminated them",
                    "reopen_reason": "docents requested larger font for tours",
                    "final_close": "printed oversize cards and added icons",
                    "followup": "Diana will verify readability during next class visit",
                },
            ),
            task(
                "Cabinet hinge squeak",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Front door hinge squeals loudly when opened.",
                participants=["Sam", "Luis", "Kyle"],
                reporter=maintainer_reporter("Sam"),
                start_offset_days=32,
                template="long_running",
                context={
                    "symptom": "cabinet hinge squealing whenever staff open it",
                    "prep": "remove the hinge pins and clean the bores",
                    "waiting_on": "waiting for dry lubricant shipment",
                    "cleaning": "Luis cleaned the door interior and Kyle vacuumed the cab",
                    "still_open": "keeping hinge off until the lube arrives",
                },
            ),
            task(
                "Spinner lane polishing",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Spinner lane drag slows balls before targets.",
                participants=["Elijah", "Jerry", "Laura"],
                reporter=maintainer_reporter("Elijah"),
                start_offset_days=44,
                template="standard_fix",
                context={
                    "symptom": "spinner lane dragging balls toward the post",
                    "prep": "tape off the spinner lane and clean the inlane",
                    "repair": "buffed the lane, adjusted the spinner, and waxed the guide",
                    "result": "spinners rip cleanly into the bonus targets",
                    "followup": "Laura will wipe fingerprints weekly to keep it slick",
                },
            ),
        ],
    ),
    machine_scenario(
        "Hokus Pokus",
        base_days_ago=210,
        tasks=[
            task(
                "Spinner relay chatter",
                task_type=Task.TYPE_PROBLEM_REPORT,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Spinner relay chatters loudly whenever lit.",
                participants=["Elijah", "Ken", "Eddie"],
                reporter=visitor_reporter("Magic show visitor", "magic@theflip.com"),
                start_offset_days=0,
                template="standard_fix",
                context={
                    "symptom": "spinner relay chattering and dropping power",
                    "prep": "pull the relay bank and inspect contacts",
                    "repair": "reset the contact gaps and replaced a weak spring",
                    "result": "relay now holds solid through full spins",
                    "followup": "Eddie will listen for chatter during cleaning",
                },
            ),
            task(
                "Add-a-ball count stuck",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Add-a-ball count stays at zero even after qualifying shots.",
                participants=["Alex", "Ben", "Chris"],
                reporter=maintainer_reporter("Alex"),
                start_offset_days=12,
                template="breakdown",
                context={
                    "symptom": "add-a-ball count stuck at zero",
                    "cause": "a frozen stepper and tarnished wiper",
                    "plan": "tear down the unit and rebuild the pawl",
                    "bench": "Chris ultrasonic-cleaned the parts and Ben reset the tension",
                    "result": "counter now advances reliably",
                    "followup": "Alex will verify counts during wizard mode demo",
                },
            ),
            task(
                "Chime box muted",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Chime box barely audible during play.",
                participants=["Elijah", "Ken", "Luis"],
                reporter=maintainer_reporter("Ken"),
                start_offset_days=24,
                template="status_cycle",
                context={
                    "symptom": "chime box barely audible on hits",
                    "plan": "clean plungers and re-seat the grommets",
                    "close_summary": "polished plungers and tightened the frame",
                    "reopen_reason": "Luis noticed the mute return after a move to storage",
                    "final_close": "added felt spacers and retightened mounts",
                    "followup": "Elijah logged a chime test before next party rental",
                },
            ),
            task(
                "Shooter lane touch-up",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Shooter lane art needs touch-up before open house.",
                participants=["Sam", "Laura", "Reba"],
                reporter=maintainer_reporter("Laura"),
                start_offset_days=36,
                template="long_running",
                context={
                    "symptom": "shooter lane artwork showing bare wood",
                    "prep": "sand the lane and mask the art",
                    "waiting_on": "waiting for matching pigments from the art shop",
                    "cleaning": "Sam re-grained the lane while Reba matched lettering",
                    "still_open": "holding final clear until pigments arrive",
                },
            ),
            task(
                "Return gate spring weak",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_STUCK_BALL,
                problem_text="Return gate barely closes after feeding the inlane.",
                participants=["Elijah", "Ken", "Eddie"],
                reporter=maintainer_reporter("Elijah"),
                start_offset_days=48,
                template="standard_fix",
                context={
                    "symptom": "return gate drifting open after a flip",
                    "prep": "remove the gate and inspect the spring",
                    "repair": "installed a new spring and polished the pivot",
                    "result": "gate now snaps shut keeping balls on the right lane",
                    "followup": "Ken will relube it during the next coil check",
                },
            ),
        ],
    ),
    machine_scenario(
        "Star Trip",
        base_days_ago=190,
        tasks=[
            task(
                "MPU battery corrosion",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Legacy NiCad leaked onto the MPU battery area.",
                participants=["Alex", "Ben", "Chris"],
                reporter=maintainer_reporter("Alex"),
                start_offset_days=0,
                template="breakdown",
                context={
                    "symptom": "alkaline fuzz around the battery holder",
                    "cause": "old NiCad leak across traces",
                    "plan": "neutralize the area and install remote batteries",
                    "bench": "Chris scrubbed the board while Ben jumpered eaten traces",
                    "result": "board boots cleanly with a remote battery pack",
                    "followup": "Alex will recheck voltage during quarterly audits",
                },
            ),
            task(
                "Lamp matrix ghosting",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Lamp matrix shows cross-fade between columns.",
                participants=["Ben", "Brian", "Josh"],
                reporter=maintainer_reporter("Ben"),
                start_offset_days=10,
                template="standard_fix",
                context={
                    "symptom": "matrix lamps ghosting on idle",
                    "prep": "scope the lamp driver board",
                    "repair": "installed fresh SCRs and cleaned headers",
                    "result": "matrix drives with crisp on/off states",
                    "followup": "Josh will run lamp test after relocations",
                },
            ),
            task(
                "Saucer kickout weak",
                task_type=Task.TYPE_PROBLEM_REPORT,
                problem_type=Task.PROBLEM_STUCK_BALL,
                problem_text="Center saucer double-fires to eject the ball.",
                participants=["Brian", "Alex", "Justin"],
                reporter=visitor_reporter("Retro league player", "retro@theflip.com"),
                start_offset_days=20,
                template="reopen_cycle",
                context={
                    "symptom": "saucer needing two attempts to kick the ball",
                    "prep": "pull the coil, clean sleeve, and check voltage",
                    "initial_fix": "installed a new sleeve and tightened the bracket",
                    "reopen_trigger": "Justin saw weak kicks return after long heat soak",
                    "second_fix": "added a new coil stop and shimmed the saucer wall",
                    "final_result": "kickout now fires with authority every time",
                    "followup": "Brian logged coil temps for the next audit",
                },
            ),
            task(
                "Sound board hum",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Low hum on attract mode audio.",
                participants=["Chris", "Alex", "David"],
                reporter=maintainer_reporter("Chris"),
                start_offset_days=32,
                template="status_cycle",
                context={
                    "symptom": "65Hz hum through the speakers",
                    "plan": "replace filter caps and reroute grounds",
                    "close_summary": "recapped the board and twisted the harness",
                    "reopen_reason": "David heard hum creep back after moving the cabinet",
                    "final_close": "added isolation washers and separated the harness bundle",
                    "followup": "Alex will re-verify noise floor during shows",
                },
            ),
            task(
                "Drop target opto clean",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Drop target optos miscount when dusty.",
                participants=["Ben", "Justin", "Josh"],
                reporter=maintainer_reporter("Ben"),
                start_offset_days=44,
                template="long_running",
                context={
                    "symptom": "drop target optos occasionally missing a drop",
                    "prep": "pull target bank and inspect opto boards",
                    "waiting_on": "waiting for spare opto boards from a donor game",
                    "cleaning": "Justin cleaned opto windows while Josh vacuumed the cab",
                    "still_open": "keeping task open until the donor boards arrive",
                },
            ),
        ],
    ),
    machine_scenario(
        "Star Trek",
        base_days_ago=170,
        tasks=[
            task(
                "Sound board recap",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Voices warble because the sound board caps dried out.",
                participants=["Alex", "Ben", "Chris"],
                reporter=maintainer_reporter("Chris"),
                start_offset_days=0,
                template="breakdown",
                context={
                    "symptom": "sound board warbling voices",
                    "cause": "filter caps dried out and ESR spiked",
                    "plan": "recap the board and verify audio rails",
                    "bench": "Ben recapped while Alex checked the audio scope traces",
                    "result": "voices sound crisp again",
                    "followup": "Chris will re-test before each event night",
                },
            ),
            task(
                "Drop target memory fault",
                task_type=Task.TYPE_PROBLEM_REPORT,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Memory drop bank forgets status mid-ball.",
                participants=["Brian", "Alex", "Justin"],
                reporter=visitor_reporter("League scorekeeper", "stleague@theflip.com"),
                start_offset_days=12,
                template="reopen_cycle",
                context={
                    "symptom": "drop target memory resetting mid-ball",
                    "prep": "ohm out the target wiring and check switch matrix",
                    "initial_fix": "re-soldered a cracked header and reseated the target harness",
                    "reopen_trigger": "issue returned when cabinet warmed up",
                    "second_fix": "added new IDC connector and tied the harness",
                    "final_result": "memory locks stay in sync through full games",
                    "followup": "Justin logged matrix values for future diagnostics",
                },
            ),
            task(
                "Cabinet harness tidy",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Cabinet wiring still messy from prior operator hacks.",
                participants=["David", "Matt", "Nick"],
                reporter=maintainer_reporter("David"),
                start_offset_days=24,
                template="long_running",
                context={
                    "symptom": "cabinet harness twisted with leftover operator hacks",
                    "prep": "label every branch and plan a reroute",
                    "waiting_on": "waiting for new wire lacing and ID tags",
                    "cleaning": "Matt wiped the cab base while Nick gathered measurements",
                    "still_open": "keeping task open until the full reroute is completed",
                },
            ),
            task(
                "Spinner opto flaky",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Spinner awards random counts.",
                participants=["Alex", "Josh", "Justin"],
                reporter=maintainer_reporter("Josh"),
                start_offset_days=36,
                template="standard_fix",
                context={
                    "symptom": "spinner opto missing spins randomly",
                    "prep": "scope the opto board and clean the spinner",
                    "repair": "replaced the opto pair and cleaned the spinner bushings",
                    "result": "spinner now registers every rip",
                    "followup": "Justin will re-run switch edge test monthly",
                },
            ),
            task(
                "Backbox insert dim",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Enterprise insert dims after 30 minutes on.",
                participants=["Ben", "Chris", "Brian"],
                reporter=maintainer_reporter("Ben"),
                start_offset_days=48,
                template="status_cycle",
                context={
                    "symptom": "Enterprise insert dimming after warm-up",
                    "plan": "add heat sinks and reflow solder",
                    "close_summary": "reflowed the lamp board and added foil shields",
                    "reopen_reason": "Brian saw dimming return during a party",
                    "final_close": "converted that insert to a low-heat LED with diffuser",
                    "followup": "Chris will check brightness before each open house",
                },
            ),
        ],
    ),
    machine_scenario(
        "Gorgar",
        base_days_ago=150,
        tasks=[
            task(
                "Magnet grabbing late",
                task_type=Task.TYPE_PROBLEM_REPORT,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Gorgar magnet barely catches the ball during speech.",
                participants=["Alex", "Ben", "Brian"],
                reporter=visitor_reporter("Classic night attendee", "classic@theflip.com"),
                start_offset_days=0,
                template="breakdown",
                context={
                    "symptom": "magnet energizing late and letting ball roll away",
                    "cause": "tired driver transistor and loose harness",
                    "plan": "rebuild the driver and verify magnet resistance",
                    "bench": "Ben swapped the driver transistor while Brian checked timing",
                    "result": "magnet now snatches the ball right on cue",
                    "followup": "Alex will re-test before the next show",
                },
            ),
            task(
                "Speech sync drifts",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Speech and lights drift out of sync mid-evening.",
                participants=["Chris", "David", "Nick"],
                reporter=maintainer_reporter("Chris"),
                start_offset_days=12,
                template="status_cycle",
                context={
                    "symptom": "speech fire cues no longer match the lights",
                    "plan": "recap the speech board and reseat ribbon cables",
                    "close_summary": "recapped and cleaned the cable ends",
                    "reopen_reason": "Nick heard it drift again during late play",
                    "final_close": "added ferrite beads and reflowed the decoder pins",
                    "followup": "David will double-check sync during Friday league",
                },
            ),
            task(
                "Playfield swap staging",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Staging donor playfield swap; tracking prep steps.",
                participants=["Ben", "Matt", "Mike"],
                reporter=maintainer_reporter("Ben"),
                start_offset_days=24,
                template="long_running",
                context={
                    "symptom": "prep checklist incomplete for playfield swap",
                    "prep": "catalog every harness and bag hardware",
                    "waiting_on": "waiting for tumbling media and clear-coated inserts",
                    "cleaning": "Matt labeled every lamp socket while Mike polished guides",
                    "still_open": "keeping this open until swap day arrives",
                },
            ),
            task(
                "Power supply rebuild",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="5V rail sagging under multiball load.",
                participants=["Alex", "Chris", "Brian"],
                reporter=maintainer_reporter("Alex"),
                start_offset_days=36,
                template="standard_fix",
                context={
                    "symptom": "5V rail drooping during multiball",
                    "prep": "pull the power board and check connectors",
                    "repair": "installed new caps, regulator, and repinned headers",
                    "result": "voltage stays tight even with all lamps on",
                    "followup": "Brian will log voltage during monthly checks",
                },
            ),
            task(
                "Spinner lane rework",
                task_type=Task.TYPE_PROBLEM_REPORT,
                problem_type=Task.PROBLEM_STUCK_BALL,
                problem_text="Spinner lane divot traps balls near the top rollovers.",
                participants=["Ben", "Justin", "Josh"],
                reporter=visitor_reporter("Retro tournament player", "retrofinals@theflip.com"),
                start_offset_days=48,
                template="reopen_cycle",
                context={
                    "symptom": "spinner lane divot catching the ball mid-spin",
                    "prep": "fill the divot and sand the guide",
                    "initial_fix": "laid down epoxy and re-waxed the lane",
                    "reopen_trigger": "divot reappeared after a hot weekend",
                    "second_fix": "installed a mylar patch and reinforced the guide",
                    "final_result": "lane now keeps speed through the spinner",
                    "followup": "Josh will inspect after each major event",
                },
            ),
        ],
    ),
    machine_scenario(
        "Blackout",
        base_days_ago=130,
        tasks=[
            task(
                "Lamp strobing on attract",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Attract mode lamps strobe wildly when cabinet warms up.",
                participants=["Alex", "Ben", "Josh"],
                reporter=maintainer_reporter("Alex"),
                start_offset_days=0,
                template="standard_fix",
                context={
                    "symptom": "lamp strobing during attract mode",
                    "prep": "reseat connectors and check lamp driver voltages",
                    "repair": "repinned the connectors and replaced failing SCRs",
                    "result": "attract mode fades smoothly again",
                    "followup": "Josh will monitor after long party nights",
                },
            ),
            task(
                "Speech board volume drop",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Speech fades out after ten minutes.",
                participants=["Chris", "Brian", "Justin"],
                reporter=maintainer_reporter("Chris"),
                start_offset_days=10,
                template="breakdown",
                context={
                    "symptom": "speech volume fading after warm-up",
                    "cause": "aging op-amp and cracked header",
                    "plan": "swap the op-amp, recap, and repin the header",
                    "bench": "Brian installed the parts while Justin dialed levels",
                    "result": "speech holds steady for entire games",
                    "followup": "Chris will check again before hosting tournaments",
                },
            ),
            task(
                "Right inlane switch flaky",
                task_type=Task.TYPE_PROBLEM_REPORT,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Right inlane switch only registers half the time.",
                participants=["Ben", "Josh", "Matt"],
                reporter=visitor_reporter("High score chaser", "blackout@theflip.com"),
                start_offset_days=22,
                template="reopen_cycle",
                context={
                    "symptom": "right inlane switch missing hits",
                    "prep": "clean the switch and test in switch edge mode",
                    "initial_fix": "polished the leafs and reset the gap",
                    "reopen_trigger": "after moving the game the switch drifted again",
                    "second_fix": "installed a new switch and added a brace",
                    "final_result": "switch now fires on every feed",
                    "followup": "Matt logged a reminder to re-test monthly",
                },
            ),
            task(
                "Drop target reset coil cooked",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Reset coil gets too hot during multiball marathons.",
                participants=["Alex", "Ben", "Chris"],
                reporter=maintainer_reporter("Ben"),
                start_offset_days=34,
                template="standard_fix",
                context={
                    "symptom": "drop target reset coil cooking itself",
                    "prep": "measure coil resistance and inspect driver transistor",
                    "repair": "installed a fresh coil, new stop, and driver transistor",
                    "result": "bank resets snappier and stays cool",
                    "followup": "Chris will shoot infrared temps after long runs",
                },
            ),
            task(
                "Cabinet ground braid audit",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Ground braid hacked by prior operator; needs redo.",
                participants=["Brian", "Nick", "Matt"],
                reporter=maintainer_reporter("Brian"),
                start_offset_days=46,
                template="long_running",
                context={
                    "symptom": "cabinet ground braid spliced with random wire",
                    "prep": "document existing braid path and plan replacements",
                    "waiting_on": "waiting for new braid rolls and staples",
                    "cleaning": "Nick vacuumed the cab while Matt labeled harnesses",
                    "still_open": "holding completion until new braid arrives",
                },
            ),
        ],
    ),
    machine_scenario(
        "Hyperball",
        base_days_ago=110,
        tasks=[
            task(
                "Ball cannon jams",
                task_type=Task.TYPE_PROBLEM_REPORT,
                problem_type=Task.PROBLEM_STUCK_BALL,
                problem_text="Ball cannon jams every few salvos.",
                participants=["Chris", "Alex", "David"],
                reporter=visitor_reporter("Hyperball league", "hyperleague@theflip.com"),
                start_offset_days=0,
                template="breakdown",
                context={
                    "symptom": "ball cannon jamming mid-volley",
                    "cause": "dirty feed rollers and glazed sleeves",
                    "plan": "tear down the cannon and rebuild rollers",
                    "bench": "Alex resurfaced rollers while David reset tolerances",
                    "result": "cannon now feeds non-stop through the whole round",
                    "followup": "Chris will recheck after each tournament",
                },
            ),
            task(
                "Cooling fan howl",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Rear cooling fan howls when running full speed.",
                participants=["Ben", "Brian", "Eddie"],
                reporter=maintainer_reporter("Ben"),
                start_offset_days=12,
                template="status_cycle",
                context={
                    "symptom": "rear fan howling whenever the cannon spins up",
                    "plan": "replace the fan and add vibration pads",
                    "close_summary": "installed a quiet fan and rubber grommets",
                    "reopen_reason": "Eddie heard a new vibration after transport",
                    "final_close": "shifted the fan mount and secured the wiring",
                    "followup": "Brian will listen during the weekly stress test",
                },
            ),
            task(
                "Opto sensors dusty",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Lane optos miscount balls because of dust.",
                participants=["Chris", "Ethan", "Luis"],
                reporter=maintainer_reporter("Chris"),
                start_offset_days=24,
                template="standard_fix",
                context={
                    "symptom": "lane optos missing a few shots",
                    "prep": "pull the opto boards and clean the brackets",
                    "repair": "polished lenses and reseated the harness",
                    "result": "optos count every ball again",
                    "followup": "Luis will add them to the weekly wipe-down list",
                },
            ),
            task(
                "Auto-loader belt stretch",
                task_type=Task.TYPE_PROBLEM_REPORT,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Auto-loader pauses when belt slips.",
                participants=["David", "Alex", "Justin"],
                reporter=visitor_reporter("Night ops volunteer", "nightops@theflip.com"),
                start_offset_days=36,
                template="reopen_cycle",
                context={
                    "symptom": "auto-loader belt slipping during rapid fire",
                    "prep": "clean the pulleys and retension the belt",
                    "initial_fix": "tightened the belt and conditioned the rubber",
                    "reopen_trigger": "belt stretch returned after a week on route",
                    "second_fix": "installed a new belt and added an idler spring",
                    "final_result": "loader keeps up with max fire rate now",
                    "followup": "Justin will recheck belt tension monthly",
                },
            ),
            task(
                "Cabinet filter schedule",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Need recurring task to replace intake filters.",
                participants=["Chris", "Eddie", "Luis"],
                reporter=maintainer_reporter("Chris"),
                start_offset_days=48,
                template="long_running",
                context={
                    "symptom": "cabinet filters clog quickly during events",
                    "prep": "document the replacement interval",
                    "waiting_on": "waiting for bulk filter order to arrive",
                    "cleaning": "Eddie vacuumed vents while Luis wiped cabinet panels",
                    "still_open": "keeping task open until filter stock arrives",
                },
            ),
        ],
    ),
    machine_scenario(
        "Eight Ball Deluxe Limited Edition",
        base_days_ago=90,
        tasks=[
            task(
                "Inline drop shorts",
                task_type=Task.TYPE_PROBLEM_REPORT,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Inline drops award random points because of shorts.",
                participants=["Alex", "Ben", "Chris"],
                reporter=visitor_reporter("Billiards fan", "ebd@theflip.com"),
                start_offset_days=0,
                template="breakdown",
                context={
                    "symptom": "inline drop targets awarding phantom points",
                    "cause": "frayed harness rubbing on the reset bar",
                    "plan": "rebuild the harness and insulate the bar",
                    "bench": "Ben built a new harness while Chris sleeved the wiring",
                    "result": "drops now score only when hit",
                    "followup": "Alex logged another inspection after the next league",
                },
            ),
            task(
                "Top saucer rejects",
                task_type=Task.TYPE_PROBLEM_REPORT,
                problem_type=Task.PROBLEM_STUCK_BALL,
                problem_text="Top saucer spits the ball back out slowly.",
                participants=["Brian", "David", "Josh"],
                reporter=visitor_reporter("League coordinator", "eightball@theflip.com"),
                start_offset_days=10,
                template="reopen_cycle",
                context={
                    "symptom": "saucer rejecting balls slowly back down",
                    "prep": "pull the coil and inspect the kicker arm",
                    "initial_fix": "cleaned the arm and added a fresh sleeve",
                    "reopen_trigger": "after long play it sagged again",
                    "second_fix": "installed a stronger spring and adjusted the guide",
                    "final_result": "saucer now fires the ball cleanly up top",
                    "followup": "Josh will keep an eye on it during tournaments",
                },
            ),
            task(
                "Feature lamp dimming",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Feature lamps dim after 20 minutes of play.",
                participants=["Alex", "Ben", "Justin"],
                reporter=maintainer_reporter("Justin"),
                start_offset_days=22,
                template="status_cycle",
                context={
                    "symptom": "feature lamps dimming as the game warms",
                    "plan": "swap in LEDs and reflow headers",
                    "close_summary": "installed warm LEDs and cleaned connectors",
                    "reopen_reason": "dim returned when the lamp board flexed",
                    "final_close": "added support brackets and retightened screws",
                    "followup": "Ben scheduled a check before every league bank",
                },
            ),
            task(
                "Cabinet decal clean-up",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Need gentle cleaning plan for the rare LE decals.",
                participants=["Laura", "Reba", "Diana"],
                reporter=maintainer_reporter("Laura"),
                start_offset_days=34,
                template="long_running",
                context={
                    "symptom": "LE cabinet decals dull from fingerprints",
                    "prep": "test mild cleaners on hidden sections",
                    "waiting_on": "waiting for museum-grade wipes to arrive",
                    "cleaning": "Reba drafted signage while Diana logged techniques",
                    "still_open": "keeping cabinet roped off until wipes arrive",
                },
            ),
            task(
                "Apron scorecard refresh",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Apron cards faded from sun exposure.",
                participants=["Alex", "Reba", "Laura"],
                reporter=maintainer_reporter("Reba"),
                start_offset_days=46,
                template="standard_fix",
                context={
                    "symptom": "scorecards faded and hard to read",
                    "prep": "scan originals and color-correct",
                    "repair": "printed new cards and sealed them under mylar",
                    "result": "cards pop again with crisp lettering",
                    "followup": "Laura added UV film to the glass to keep them fresh",
                },
            ),
        ],
    ),
    machine_scenario(
        "The Getaway: High Speed II",
        base_days_ago=70,
        tasks=[
            task(
                "Supercharger running slow",
                task_type=Task.TYPE_PROBLEM_REPORT,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Supercharger loop can't break 90MPH.",
                participants=["David", "Alex", "Ben"],
                reporter=visitor_reporter("HS2 league", "getaway@theflip.com"),
                start_offset_days=0,
                template="breakdown",
                context={
                    "symptom": "supercharger struggling to spin the ball fast",
                    "cause": "dirty magnets and tired driver board caps",
                    "plan": "clean the loop and rebuild the driver",
                    "bench": "Alex recapped the board while Ben polished the rails",
                    "result": "loop now pegs the speedometer again",
                    "followup": "David set a reminder to re-test monthly",
                },
            ),
            task(
                "Trough opto dropout",
                task_type=Task.TYPE_PROBLEM_REPORT,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Trough shows phantom empty during multiball.",
                participants=["Brian", "Josh", "Justin"],
                reporter=visitor_reporter("Midweek league", "midweek@theflip.com"),
                start_offset_days=10,
                template="reopen_cycle",
                context={
                    "symptom": "trough opto dropping one position mid-game",
                    "prep": "clean the opto pair and reseat IDC",
                    "initial_fix": "polished lenses and repinned the connector",
                    "reopen_trigger": "after transport the fault returned",
                    "second_fix": "installed a new opto board and rerouted the harness",
                    "final_result": "trough counts stay stable through chaos",
                    "followup": "Justin added trough checks to the event checklist",
                },
            ),
            task(
                "Diverter clunk",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Ramp diverter clunks loudly when grabbing the ball.",
                participants=["David", "Mark", "Tyler"],
                reporter=maintainer_reporter("David"),
                start_offset_days=22,
                template="status_cycle",
                context={
                    "symptom": "left ramp diverter clunking and shaking the cab",
                    "plan": "rebuild the mech and pad the stop",
                    "close_summary": "installed new bushings and felt pads",
                    "reopen_reason": "Tyler heard the clunk return after a road case trip",
                    "final_close": "added a coil sleeve and tightened the bracket",
                    "followup": "Mark will listen for clunks during warm-up",
                },
            ),
            task(
                "Shifter switch intermittent",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Gear shifter sometimes fails to start video mode.",
                participants=["Alex", "Brian", "Josh"],
                reporter=maintainer_reporter("Alex"),
                start_offset_days=34,
                template="standard_fix",
                context={
                    "symptom": "shifter switch missing activations",
                    "prep": "pull the handle and inspect the leaf stack",
                    "repair": "installed a new microswitch and adjusted the actuator",
                    "result": "video mode now starts every pull",
                    "followup": "Brian will keep switch lube handy during PMs",
                },
            ),
            task(
                "Beacon maintenance",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Roof beacon needs regular cleaning and bearing oil.",
                participants=["David", "Eddie", "Luis"],
                reporter=maintainer_reporter("David"),
                start_offset_days=46,
                template="long_running",
                context={
                    "symptom": "beacon lens hazy and bearings dry",
                    "prep": "log a quarterly clean-and-oil plan",
                    "waiting_on": "waiting for replacement lens gasket",
                    "cleaning": "Eddie polished the lens while Luis wiped the housing",
                    "still_open": "holding close until gasket arrives",
                },
            ),
        ],
    ),
    machine_scenario(
        "The Addams Family",
        base_days_ago=50,
        tasks=[
            task(
                "Thing hand alignment",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Thing hand drops the ball off-center.",
                participants=["David", "Alex", "Ben"],
                reporter=maintainer_reporter("David"),
                start_offset_days=0,
                template="breakdown",
                context={
                    "symptom": "Thing hand dropping balls toward the slings",
                    "cause": "loose hand bracket and worn rubber grommet",
                    "plan": "realign the mech and replace the grommet",
                    "bench": "Alex rebuilt the mech while Ben dialed in the linkage",
                    "result": "hand now places balls squarely in the lane",
                    "followup": "David will recheck alignment after transport",
                },
            ),
            task(
                "Bookcase opto intermittent",
                task_type=Task.TYPE_PROBLEM_REPORT,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Bookcase fails to spin sometimes.",
                participants=["Brian", "Josh", "Justin"],
                reporter=visitor_reporter("Thing flips competitor", "taf@theflip.com"),
                start_offset_days=8,
                template="reopen_cycle",
                context={
                    "symptom": "bookcase opto intermittently failing",
                    "prep": "clean the opto and reseat connectors",
                    "initial_fix": "cleaned the opto pair and secured the harness",
                    "reopen_trigger": "fault returned after the game warmed up",
                    "second_fix": "installed new optos and added heat shielding",
                    "final_result": "bookcase now spins on cue every time",
                    "followup": "Justin logged opto voltage readings for reference",
                },
            ),
            task(
                "Power driver board refresh",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Driver board caps bulging; refresh needed.",
                participants=["Alex", "Ben", "Chris"],
                reporter=maintainer_reporter("Alex"),
                start_offset_days=16,
                template="standard_fix",
                context={
                    "symptom": "driver board showing ripple in 12V rail",
                    "prep": "pull the board and inspect caps",
                    "repair": "recapped the board and repinned J101/J102",
                    "result": "voltage rails rock solid again",
                    "followup": "Chris will re-scope rails quarterly",
                },
            ),
            task(
                "Swamp kickout rejects",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_STUCK_BALL,
                problem_text="Swamp kickout dribbles the ball down the middle.",
                participants=["David", "Brian", "Josh"],
                reporter=maintainer_reporter("Brian"),
                start_offset_days=24,
                template="status_cycle",
                context={
                    "symptom": "swamp kickout rolling SDTM",
                    "plan": "adjust the scoop and add foam",
                    "close_summary": "shimmed the scoop and added dead foam",
                    "reopen_reason": "Josh reported dribbles returning after leveling",
                    "final_close": "re-bent the guide and increased coil power slightly",
                    "followup": "David scheduled another test after the next event",
                },
            ),
            task(
                "GI connector burn",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="General illumination connector shows heat damage.",
                participants=["Alex", "Ben", "Laura"],
                reporter=maintainer_reporter("Ben"),
                start_offset_days=32,
                template="long_running",
                context={
                    "symptom": "GI connector browning from heat",
                    "prep": "document connectors and order trifurcon pins",
                    "waiting_on": "waiting for the pin kit and tool loaner",
                    "cleaning": "Laura wiped the braids while Alex labeled harnesses",
                    "still_open": "holding close until new pins are installed",
                },
            ),
        ],
    ),
    machine_scenario(
        "Godzilla (Premium)",
        base_days_ago=20,
        tasks=[
            task(
                "Insider Connected Wi-Fi dropouts",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Wi-Fi module drops Insider Connected during busy nights.",
                participants=["David", "Brian", "Tyler"],
                reporter=maintainer_reporter("David"),
                start_offset_days=0,
                template="status_cycle",
                context={
                    "symptom": "Wi-Fi module dropping connection mid-queue",
                    "plan": "relocate the access point antenna",
                    "close_summary": "moved the AP closer and reconfigured channels",
                    "reopen_reason": "Tyler saw dropouts return when the hall filled",
                    "final_close": "ran ethernet to the cab and disabled flaky Wi-Fi",
                    "followup": "Brian will monitor Insider Connected health weekly",
                },
            ),
            task(
                "Building mech catches",
                task_type=Task.TYPE_PROBLEM_REPORT,
                problem_type=Task.PROBLEM_STUCK_BALL,
                problem_text="Building mech catches balls on level three.",
                participants=["Alex", "Ben", "Brian"],
                reporter=visitor_reporter("Modern night competitor", "modern@theflip.com"),
                start_offset_days=4,
                template="breakdown",
                context={
                    "symptom": "building mech catching balls on the third floor",
                    "cause": "misaligned roof flap and dragging post sleeve",
                    "plan": "tear down the mech and realign the flap",
                    "bench": "Ben adjusted the linkage while Brian deburred the flap",
                    "result": "balls roll cleanly across all building levels",
                    "followup": "Alex will re-test before the next tournament stream",
                },
            ),
            task(
                "Magna Grab sensitivity",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Magna Grab too sensitive and snags random balls.",
                participants=["David", "Chris", "Eddie"],
                reporter=maintainer_reporter("Chris"),
                start_offset_days=8,
                template="reopen_cycle",
                context={
                    "symptom": "Magna Grab taking random balls on left orbit",
                    "prep": "adjust magnet strength and test in diagnostics",
                    "initial_fix": "recalibrated the node board setting",
                    "reopen_trigger": "after new code install it reverted",
                    "second_fix": "loaded custom settings and re-tuned the magnet window",
                    "final_result": "magnet now grabs only on scripted moments",
                    "followup": "Eddie will note behavior during leagues",
                },
            ),
            task(
                "Bridge mech squeak",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Bridge mech squeaks loudly during collapse.",
                participants=["Ben", "Luis", "Caleb"],
                reporter=maintainer_reporter("Ben"),
                start_offset_days=10,
                template="standard_fix",
                context={
                    "symptom": "bridge collapse squeaking loudly",
                    "prep": "remove the bridge assembly and inspect pivots",
                    "repair": "lubed pivots, replaced sleeves, and adjusted coils",
                    "result": "collapse is smooth and quiet now",
                    "followup": "Luis will dust the mech weekly to keep it clean",
                },
            ),
            task(
                "Code update checklist",
                task_type=Task.TYPE_TASK,
                problem_type=Task.PROBLEM_OTHER,
                problem_text="Need repeatable checklist for frequent code drops.",
                participants=["David", "Brian", "Tyler"],
                reporter=maintainer_reporter("Brian"),
                start_offset_days=12,
                template="long_running",
                context={
                    "symptom": "code updates causing one-off issues when rushed",
                    "prep": "document a step-by-step update checklist",
                    "waiting_on": "waiting for Stern to publish the next minor build",
                    "cleaning": "Tyler backed up audits while David captured screenshots",
                    "still_open": "keeping task open until checklist is vetted by volunteers",
                },
            ),
        ],
    ),
]
