"""Tests for the Owner model and owner views."""

from constance.test import override_config
from django.test import TestCase, tag
from django.urls import reverse

from flipfix.apps.catalog.models import Owner
from flipfix.apps.core.test_utils import (
    TestDataMixin,
    create_machine,
    create_machine_model,
    create_superuser,
)


@tag("models")
class OwnerModelTests(TestCase):
    """Tests for the Owner model."""

    def test_str_returns_name(self):
        """__str__ should return the owner name."""
        owner = Owner.objects.create(name="Test Owner")
        self.assertEqual(str(owner), "Test Owner")

    def test_slug_auto_generated(self):
        """Slug should be auto-generated from name."""
        owner = Owner.objects.create(name="Jane Smith")
        self.assertEqual(owner.slug, "jane-smith")

    def test_slug_uniqueness(self):
        """Slugs should be unique even with similar names."""
        owner1 = Owner.objects.create(name="Test Owner")
        owner2 = Owner.objects.create(name="Test Owner--")
        self.assertEqual(owner1.slug, "test-owner")
        self.assertNotEqual(owner1.slug, owner2.slug)

    def test_get_absolute_url(self):
        """get_absolute_url should return the detail page URL."""
        owner = Owner.objects.create(name="Test Owner")
        self.assertEqual(owner.get_absolute_url(), f"/owners/{owner.slug}/")


@tag("models")
class MachineOwnerRelationshipTests(TestCase):
    """Tests for the MachineInstance-Owner FK relationship."""

    def test_machine_with_owner(self):
        """A machine can have an owner."""
        owner = Owner.objects.create(name="Test Owner")
        machine = create_machine(owner=owner)
        machine.refresh_from_db()
        self.assertEqual(machine.owner, owner)

    def test_machine_without_owner(self):
        """A machine can have no owner (nullable FK)."""
        machine = create_machine()
        self.assertIsNone(machine.owner)

    def test_owner_machines_related_name(self):
        """Owner.machines should list machines via the reverse FK."""
        owner = Owner.objects.create(name="Test Owner")
        model = create_machine_model()
        m1 = create_machine(model=model, name="Machine A", owner=owner)
        m2 = create_machine(model=model, name="Machine B", owner=owner)
        self.assertEqual(set(owner.machines.all()), {m1, m2})

    def test_ownership_display_with_owner(self):
        """ownership_display should return the owner's name."""
        owner = Owner.objects.create(name="Jane Smith")
        machine = create_machine(owner=owner)
        self.assertEqual(machine.ownership_display, "Jane Smith")

    def test_ownership_display_without_owner(self):
        """ownership_display should return default when no owner."""
        machine = create_machine()
        self.assertEqual(machine.ownership_display, "The Flip Collection")

    def test_deleting_owner_nullifies_machines(self):
        """Deleting an owner should set machine.owner to NULL (SET_NULL)."""
        owner = Owner.objects.create(name="Temp Owner")
        machine = create_machine(owner=owner)
        owner.delete()
        machine.refresh_from_db()
        self.assertIsNone(machine.owner)


@tag("views")
class OwnerListViewTests(TestDataMixin, TestCase):
    """Tests for the owner list view."""

    def test_list_page_loads(self):
        """Owner list page should load for maintainers."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(reverse("owner-list"))
        self.assertEqual(response.status_code, 200)

    def test_list_shows_owners(self):
        """Owner list should show all owners."""
        Owner.objects.create(name="Owner A")
        Owner.objects.create(name="Owner B")
        self.client.force_login(self.maintainer_user)
        response = self.client.get(reverse("owner-list"))
        self.assertContains(response, "Owner A")
        self.assertContains(response, "Owner B")

    def test_list_shows_machine_counts(self):
        """Owner list should annotate machine counts."""
        owner = Owner.objects.create(name="Multi-Machine Owner")
        model = create_machine_model(name="List Test Model")
        create_machine(model=model, name="M1", owner=owner)
        create_machine(model=model, name="M2", owner=owner)
        self.client.force_login(self.maintainer_user)
        response = self.client.get(reverse("owner-list"))
        self.assertContains(response, "2 machines")


@tag("views")
class OwnerDetailViewTests(TestDataMixin, TestCase):
    """Tests for the owner detail view."""

    def setUp(self):
        super().setUp()
        self.owner = Owner.objects.create(name="Detail Test Owner", email="test@example.com")

    def test_detail_page_loads(self):
        """Owner detail page should load for maintainers."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(reverse("owner-detail", kwargs={"slug": self.owner.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Detail Test Owner")

    def test_detail_shows_linked_machines(self):
        """Owner detail should show machines owned by this owner."""
        self.machine.owner = self.owner
        self.machine.save()
        self.client.force_login(self.maintainer_user)
        response = self.client.get(reverse("owner-detail", kwargs={"slug": self.owner.slug}))
        self.assertContains(response, self.machine.name)


@tag("views")
class OwnerCreateViewTests(TestDataMixin, TestCase):
    """Tests for the owner create view."""

    def test_create_page_loads(self):
        """Owner create page should load for maintainers."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(reverse("owner-create"))
        self.assertEqual(response.status_code, 200)

    def test_create_owner(self):
        """POST should create a new owner and redirect."""
        self.client.force_login(self.maintainer_user)
        response = self.client.post(
            reverse("owner-create"),
            {
                "name": "New Owner",
                "email": "new@example.com",
                "phone": "",
                "alternate_contact": "",
                "notes": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        owner = Owner.objects.get(name="New Owner")
        self.assertEqual(owner.email, "new@example.com")
        self.assertEqual(owner.created_by, self.maintainer_user)


@tag("views")
class OwnerUpdateViewTests(TestDataMixin, TestCase):
    """Tests for the owner update view."""

    def setUp(self):
        super().setUp()
        self.owner = Owner.objects.create(name="Editable Owner")

    def test_edit_page_loads(self):
        """Owner edit page should load for maintainers."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(reverse("owner-edit", kwargs={"slug": self.owner.slug}))
        self.assertEqual(response.status_code, 200)

    def test_update_owner(self):
        """POST should update the owner and redirect."""
        self.client.force_login(self.maintainer_user)
        response = self.client.post(
            reverse("owner-edit", kwargs={"slug": self.owner.slug}),
            {
                "name": "Updated Owner",
                "email": "",
                "phone": "",
                "alternate_contact": "",
                "notes": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.name, "Updated Owner")
        self.assertEqual(self.owner.updated_by, self.maintainer_user)


@tag("views")
class OwnerNavigationTests(TestCase):
    """Tests for the owner nav link visibility."""

    def test_nav_link_visible_for_superuser(self):
        """Owners nav link should be visible to superusers."""
        superuser = create_superuser()
        self.client.force_login(superuser)
        response = self.client.get(reverse("owner-list"))
        self.assertEqual(response.status_code, 200)


@tag("views")
class OwnerPrivacyTests(TestDataMixin, TestCase):
    """Owner info must not appear on public pages."""

    def setUp(self):
        super().setUp()
        self.owner = Owner.objects.create(name="Secret Owner")
        self.machine.owner = self.owner
        self.machine.save()

    @override_config(PUBLIC_ACCESS_ENABLED=True)
    def test_machine_feed_hides_owner_for_guest(self):
        """Machine feed should not show owner info to unauthenticated users."""
        url = reverse("maintainer-machine-detail", kwargs={"slug": self.machine.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Secret Owner")

    @override_config(PUBLIC_ACCESS_ENABLED=True)
    def test_machine_feed_shows_owner_for_maintainer(self):
        """Machine feed should show owner info to authenticated maintainers."""
        self.client.force_login(self.maintainer_user)
        url = reverse("maintainer-machine-detail", kwargs={"slug": self.machine.slug})
        response = self.client.get(url)
        self.assertContains(response, "Secret Owner")

    def test_public_machine_detail_hides_owner(self):
        """Public machine detail (/m/slug/) should not show owner info."""
        url = reverse("public-machine-detail", kwargs={"slug": self.machine.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Secret Owner")
