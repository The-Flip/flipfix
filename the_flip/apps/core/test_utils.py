"""Shared test utilities, factories, and mixins.

This module provides common test data factories and mixins to reduce
code duplication across test files.

Usage:
    from the_flip.apps.core.test_utils import TestDataMixin

    class MyTestCase(TestDataMixin, TestCase):
        def setUp(self):
            super().setUp()
            # self.machine, self.staff_user, etc. are now available
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from django.contrib.auth import get_user_model

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.catalog.models import MachineInstance, MachineModel
from the_flip.apps.maintenance.models import LogEntry, ProblemReport

if TYPE_CHECKING:
    from django.contrib.auth.models import User

UserModel = cast("type[User]", get_user_model())


# Counter for unique names
_counter = {"user": 0, "machine": 0, "report": 0, "log": 0}


def _next_id(key: str) -> int:
    """Get next unique ID for a given key."""
    _counter[key] += 1
    return _counter[key]


# =============================================================================
# Factory Functions
# =============================================================================


def create_user(
    username: str | None = None,
    password: str = "testpass123",  # noqa: S107
    is_staff: bool = False,
    is_superuser: bool = False,
    first_name: str = "",
    last_name: str = "",
    email: str | None = None,
    **kwargs,
) -> User:
    """Create a test user with sensible defaults.

    Args:
        username: Username (auto-generated if not provided)
        password: Password (defaults to 'testpass123')
        is_staff: Whether user is staff (maintainer)
        is_superuser: Whether user is superuser (admin)
        first_name: User's first name
        last_name: User's last name
        email: Email address (auto-generated if not provided)
        **kwargs: Additional fields passed to create_user

    Returns:
        Created User instance
    """
    if username is None:
        username = f"testuser{_next_id('user')}"
    if email is None:
        email = f"{username}@example.com"

    if is_superuser:
        return UserModel.objects.create_superuser(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            **kwargs,
        )
    return UserModel.objects.create_user(
        username=username,
        email=email,
        password=password,
        is_staff=is_staff,
        first_name=first_name,
        last_name=last_name,
        **kwargs,
    )


def create_staff_user(username: str | None = None, **kwargs) -> User:
    """Create a staff user (maintainer).

    Convenience wrapper around create_user with is_staff=True.
    """
    return create_user(username=username, is_staff=True, **kwargs)


def create_superuser(username: str | None = None, **kwargs) -> User:
    """Create a superuser (admin).

    Convenience wrapper around create_user with is_superuser=True.
    """
    return create_user(username=username, is_superuser=True, **kwargs)


def create_machine_model(
    name: str | None = None,
    manufacturer: str = "Test Manufacturer",
    year: int = 2020,
    era: str = MachineModel.ERA_SS,
    **kwargs,
) -> MachineModel:
    """Create a test MachineModel.

    Args:
        name: Machine model name (auto-generated if not provided)
        manufacturer: Manufacturer name
        year: Year of manufacture
        era: Era code (SS, EM, DMD, LCD)
        **kwargs: Additional fields

    Returns:
        Created MachineModel instance
    """
    if name is None:
        name = f"Test Machine {_next_id('machine')}"
    return MachineModel.objects.create(
        name=name,
        manufacturer=manufacturer,
        year=year,
        era=era,
        **kwargs,
    )


def create_machine(
    model: MachineModel | None = None,
    slug: str | None = None,
    operational_status: str = MachineInstance.STATUS_GOOD,
    **kwargs,
) -> MachineInstance:
    """Create a test MachineInstance.

    Args:
        model: MachineModel (created if not provided)
        slug: URL slug (auto-generated from model name if not provided)
        operational_status: Machine status (defaults to 'good')
        **kwargs: Additional fields

    Returns:
        Created MachineInstance instance
    """
    if model is None:
        model = create_machine_model()
    if slug is None:
        slug = f"test-machine-{_next_id('machine')}"
    return MachineInstance.objects.create(
        model=model,
        slug=slug,
        operational_status=operational_status,
        **kwargs,
    )


def create_problem_report(
    machine: MachineInstance | None = None,
    status: str = ProblemReport.STATUS_OPEN,
    problem_type: str = ProblemReport.PROBLEM_OTHER,
    description: str | None = None,
    **kwargs,
) -> ProblemReport:
    """Create a test ProblemReport.

    Args:
        machine: MachineInstance (created if not provided)
        status: Report status (defaults to 'open')
        problem_type: Problem type (defaults to 'other')
        description: Problem description (auto-generated if not provided)
        **kwargs: Additional fields

    Returns:
        Created ProblemReport instance
    """
    if machine is None:
        machine = create_machine()
    if description is None:
        description = f"Test problem report {_next_id('report')}"
    return ProblemReport.objects.create(
        machine=machine,
        status=status,
        problem_type=problem_type,
        description=description,
        **kwargs,
    )


def create_log_entry(
    machine: MachineInstance | None = None,
    text: str | None = None,
    created_by: User | None = None,
    **kwargs,
) -> LogEntry:
    """Create a test LogEntry.

    Args:
        machine: MachineInstance (created if not provided)
        text: Log entry text (auto-generated if not provided)
        created_by: User who created the entry
        **kwargs: Additional fields

    Returns:
        Created LogEntry instance
    """
    if machine is None:
        machine = create_machine()
    if text is None:
        text = f"Test log entry {_next_id('log')}"
    return LogEntry.objects.create(
        machine=machine,
        text=text,
        created_by=created_by,
        **kwargs,
    )


def create_shared_terminal(
    username: str | None = None,
    first_name: str = "Workshop",
    last_name: str = "Terminal",
) -> Maintainer:
    """Create a shared terminal account.

    Args:
        username: Username (auto-generated if not provided)
        first_name: Terminal display first name
        last_name: Terminal display last name

    Returns:
        Maintainer instance with is_shared_account=True
    """
    if username is None:
        username = f"terminal-{_next_id('user')}"
    user = create_staff_user(
        username=username,
        first_name=first_name,
        last_name=last_name,
    )
    maintainer = Maintainer.objects.get(user=user)
    maintainer.is_shared_account = True
    maintainer.save()
    return maintainer


# =============================================================================
# Test Mixins
# =============================================================================


class TestDataMixin:
    """Mixin that provides common test data setup.

    Provides:
        - self.machine_model: A MachineModel instance
        - self.machine: A MachineInstance instance
        - self.staff_user: A staff User (maintainer)
        - self.regular_user: A non-staff User
        - self.superuser: A superuser (admin)

    Usage:
        class MyTestCase(TestDataMixin, TestCase):
            def setUp(self):
                super().setUp()
                # Now use self.machine, self.staff_user, etc.
    """

    def setUp(self):
        """Set up common test data."""
        super().setUp()
        self.machine_model = create_machine_model(name="Test Machine")
        self.machine = create_machine(
            model=self.machine_model,
            slug="test-machine",
        )
        self.staff_user = create_staff_user(username="staffuser")
        self.regular_user = create_user(username="regularuser")
        self.superuser = create_superuser(username="admin")
