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

import shutil
import tempfile
import uuid
from typing import TYPE_CHECKING, cast

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.catalog.models import MachineInstance, MachineModel
from the_flip.apps.maintenance.models import LogEntry, ProblemReport
from the_flip.apps.parts.models import PartRequest, PartRequestUpdate

if TYPE_CHECKING:
    from django.contrib.auth.models import User

UserModel = cast("type[User]", get_user_model())

# Default password for all test users - centralized to avoid secret detection warnings
TEST_PASSWORD = "testpass123"  # noqa: S105

# Minimal valid PNG (1x1 transparent pixel) for tests that need valid image data
MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
    b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _unique_suffix() -> str:
    """Return a short unique suffix for test data."""
    return uuid.uuid4().hex[:8]


# =============================================================================
# Factory Functions
# =============================================================================


def create_user(
    username: str | None = None,
    password: str = TEST_PASSWORD,
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
        username = f"testuser-{_unique_suffix()}"
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
    """Create a staff user.

    Deprecated: Use create_maintainer_user() for maintainer portal access.
    """
    return create_user(username=username, is_staff=True, **kwargs)


def create_maintainer_user(username: str | None = None, **kwargs) -> User:
    """Create a user with maintainer portal access via Maintainers group."""
    from django.contrib.auth.models import Group

    user = create_user(username=username, is_staff=False, **kwargs)
    Maintainer.objects.get_or_create(user=user)
    group = Group.objects.get(name="Maintainers")
    user.groups.add(group)
    return user


def create_superuser(username: str | None = None, **kwargs) -> User:
    """Create a superuser (admin).

    Convenience wrapper around create_user with is_superuser=True.
    """
    return create_user(username=username, is_superuser=True, **kwargs)


def create_terminal_manager_user(username: str | None = None, **kwargs) -> User:
    """Create a user with terminal management access.

    Currently implemented via is_superuser=True.
    May switch to permission-based if terminal management is delegated in the future.
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
        name = f"Test Machine {_unique_suffix()}"
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
    skip_auto_log: bool = True,
    **kwargs,
) -> MachineInstance:
    """Create a test MachineInstance.

    Args:
        model: MachineModel (created if not provided)
        slug: URL slug (auto-generated from model name if not provided)
        operational_status: Machine status (defaults to 'good')
        skip_auto_log: Skip auto log entry creation (defaults to True for tests)
        **kwargs: Additional fields

    Returns:
        Created MachineInstance instance
    """
    if model is None:
        model = create_machine_model()
    if slug is None:
        slug = f"test-machine-{_unique_suffix()}"

    instance = MachineInstance(
        model=model,
        slug=slug,
        operational_status=operational_status,
        **kwargs,
    )
    if skip_auto_log:
        instance._skip_auto_log = True  # type: ignore[attr-defined]
    instance.save()
    return instance


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
        description = f"Test problem report {_unique_suffix()}"
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
        text = f"Test log entry {_unique_suffix()}"
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
        username = f"terminal-{_unique_suffix()}"
    user = create_maintainer_user(
        username=username,
        first_name=first_name,
        last_name=last_name,
    )
    maintainer = Maintainer.objects.get(user=user)
    maintainer.is_shared_account = True
    maintainer.save()
    return maintainer


def create_part_request(
    text: str | None = None,
    requested_by: Maintainer | None = None,
    machine: MachineInstance | None = None,
    status: str = PartRequest.STATUS_REQUESTED,
    **kwargs,
) -> PartRequest:
    """Create a test PartRequest.

    Args:
        text: Part request description (auto-generated if not provided)
        requested_by: Maintainer who requested (created if not provided)
        machine: MachineInstance (optional)
        status: Request status (defaults to 'requested')
        **kwargs: Additional fields

    Returns:
        Created PartRequest instance
    """
    if text is None:
        text = f"Test part request {_unique_suffix()}"
    if requested_by is None:
        user = create_maintainer_user()
        requested_by = Maintainer.objects.get(user=user)
    return PartRequest.objects.create(
        text=text,
        requested_by=requested_by,
        machine=machine,
        status=status,
        **kwargs,
    )


def create_part_request_update(
    part_request: PartRequest | None = None,
    posted_by: Maintainer | None = None,
    text: str | None = None,
    new_status: str = "",
    **kwargs,
) -> PartRequestUpdate:
    """Create a test PartRequestUpdate.

    Args:
        part_request: Parent PartRequest (created if not provided)
        posted_by: Maintainer who posted (created if not provided)
        text: Update text (auto-generated if not provided)
        new_status: Status change (empty if no change)
        **kwargs: Additional fields

    Returns:
        Created PartRequestUpdate instance
    """
    if part_request is None:
        part_request = create_part_request()
    if posted_by is None:
        user = create_maintainer_user()
        posted_by = Maintainer.objects.get(user=user)
    if text is None:
        text = f"Test part update {_unique_suffix()}"
    return PartRequestUpdate.objects.create(
        part_request=part_request,
        posted_by=posted_by,
        text=text,
        new_status=new_status,
        **kwargs,
    )


# =============================================================================
# Test Mixins
# =============================================================================


class SuppressRequestLogsMixin:
    """Mixin to suppress Django request logging during tests.

    Use this for test classes that intentionally trigger 4xx/5xx responses
    (e.g., testing access control, 404s, method not allowed).

    The mixin suppresses django.request logs at the class level, so all
    tests in the class run quietly, but logs are restored afterward.

    Usage:
        class MyAccessControlTests(SuppressRequestLogsMixin, TestCase):
            def test_unauthorized_returns_403(self):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 403)  # No log output

    For convenience, use AccessControlTestCase instead of mixing this in manually.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import logging

        cls._request_logger = logging.getLogger("django.request")
        cls._original_level = cls._request_logger.level
        cls._request_logger.setLevel(logging.CRITICAL)

    @classmethod
    def tearDownClass(cls):
        cls._request_logger.setLevel(cls._original_level)
        super().tearDownClass()


class AccessControlTestCase(SuppressRequestLogsMixin, TestCase):
    """TestCase for access control tests that intentionally trigger 4xx/5xx responses.

    Automatically suppresses django.request logging to avoid noisy test output
    when testing authentication, authorization, and error handling.

    Usage:
        class MyViewPermissionTests(AccessControlTestCase):
            def test_requires_login(self):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)  # No log spam

            def test_requires_staff(self):
                self.client.force_login(regular_user)
                response = self.client.get(url)
                self.assertEqual(response.status_code, 403)  # No log spam
    """

    pass


class TemporaryMediaMixin:
    """Mixin to isolate MEDIA_ROOT per test class and clean up files."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._temp_media_dir = tempfile.mkdtemp()
        cls._override_media_root = override_settings(MEDIA_ROOT=cls._temp_media_dir)
        cls._override_media_root.enable()

    @classmethod
    def tearDownClass(cls):
        cls._override_media_root.disable()
        shutil.rmtree(cls._temp_media_dir, ignore_errors=True)
        super().tearDownClass()


class TestDataMixin:
    """Mixin that provides common test data setup.

    Provides:
        - self.machine_model: A MachineModel instance
        - self.machine: A MachineInstance instance
        - self.maintainer_user: A User with maintainer portal access
        - self.staff_user: Alias for maintainer_user (deprecated)
        - self.regular_user: A User without special permissions
        - self.superuser: A superuser (admin)

    Usage:
        class MyTestCase(TestDataMixin, TestCase):
            def setUp(self):
                super().setUp()
                # Now use self.machine, self.maintainer_user, etc.
    """

    def setUp(self):
        """Set up common test data."""
        super().setUp()
        self.machine_model = create_machine_model(name="Test Machine")
        self.machine = create_machine(
            model=self.machine_model,
            slug="test-machine",
        )
        self.maintainer_user = create_maintainer_user()
        self.staff_user = self.maintainer_user  # Deprecated alias
        self.regular_user = create_user()
        self.superuser = create_superuser()
