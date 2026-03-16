"""Tests for machine and owner comments, and the machine details page."""

from django.test import TestCase, tag
from django.urls import reverse

from flipfix.apps.catalog.models import MachineComment, Owner, OwnerComment
from flipfix.apps.core.test_utils import TestDataMixin


@tag("views")
class MachineDetailsViewTests(TestDataMixin, TestCase):
    """Tests for the machine details page."""

    def test_details_page_loads(self):
        """Machine details page should load for maintainers."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(reverse("machine-details", kwargs={"slug": self.machine.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.machine.name)

    def test_details_shows_asset_id(self):
        """Machine details should display the asset ID."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(reverse("machine-details", kwargs={"slug": self.machine.slug}))
        self.assertContains(response, self.machine.asset_id)

    def test_details_shows_owner(self):
        """Machine details should show the owner if set."""
        owner = Owner.objects.create(name="Details Test Owner")
        self.machine.owner = owner
        self.machine.save()
        self.client.force_login(self.maintainer_user)
        response = self.client.get(reverse("machine-details", kwargs={"slug": self.machine.slug}))
        self.assertContains(response, "Details Test Owner")

    def test_sidebar_has_details_link(self):
        """Machine feed sidebar should have a link to the details page."""
        self.client.force_login(self.maintainer_user)
        response = self.client.get(
            reverse("maintainer-machine-detail", kwargs={"slug": self.machine.slug})
        )
        details_url = reverse("machine-details", kwargs={"slug": self.machine.slug})
        self.assertContains(response, details_url)


@tag("views")
class MachineCommentTests(TestDataMixin, TestCase):
    """Tests for creating comments on machines."""

    def test_add_comment(self):
        """POST with add_comment should create a machine comment."""
        self.client.force_login(self.maintainer_user)
        url = reverse("machine-details", kwargs={"slug": self.machine.slug})
        response = self.client.post(
            url,
            {"action": "add_comment", "text": "This is a test comment"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.machine.comments.count(), 1)
        comment = self.machine.comments.first()
        self.assertEqual(comment.text, "This is a test comment")
        self.assertEqual(comment.posted_by, self.maintainer_user)

    def test_comment_displayed_on_details(self):
        """Comments should be visible on the machine details page."""
        MachineComment.objects.create(
            machine=self.machine,
            text="Visible comment",
            posted_by=self.maintainer_user,
        )
        self.client.force_login(self.maintainer_user)
        response = self.client.get(reverse("machine-details", kwargs={"slug": self.machine.slug}))
        self.assertContains(response, "Visible comment")

    def test_comment_not_in_feed(self):
        """Comments should NOT appear in the machine feed."""
        MachineComment.objects.create(
            machine=self.machine,
            text="Hidden from feed",
            posted_by=self.maintainer_user,
        )
        self.client.force_login(self.maintainer_user)
        response = self.client.get(
            reverse("maintainer-machine-detail", kwargs={"slug": self.machine.slug})
        )
        self.assertNotContains(response, "Hidden from feed")


@tag("views")
class OwnerCommentTests(TestDataMixin, TestCase):
    """Tests for creating comments on owners."""

    def setUp(self):
        super().setUp()
        self.owner = Owner.objects.create(name="Commentable Owner")

    def test_add_comment_to_owner(self):
        """POST with add_comment should create an owner comment."""
        self.client.force_login(self.maintainer_user)
        url = reverse("owner-detail", kwargs={"slug": self.owner.slug})
        response = self.client.post(
            url,
            {"action": "add_comment", "text": "Owner note"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.owner.comments.count(), 1)
        comment = self.owner.comments.first()
        self.assertEqual(comment.text, "Owner note")

    def test_comment_displayed_on_owner_detail(self):
        """Comments should be visible on the owner detail page."""
        OwnerComment.objects.create(
            owner=self.owner,
            text="Owner comment visible",
            posted_by=self.maintainer_user,
        )
        self.client.force_login(self.maintainer_user)
        response = self.client.get(reverse("owner-detail", kwargs={"slug": self.owner.slug}))
        self.assertContains(response, "Owner comment visible")
