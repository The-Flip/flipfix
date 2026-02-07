"""Wiki signals: reference cleanup, tag sentinel management."""

from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from the_flip.apps.core.models import RecordReference

from .models import UNTAGGED_SENTINEL, WikiPage, WikiPageTag


@receiver(post_delete, sender=WikiPage)
def cleanup_wiki_references(sender, instance, **kwargs):
    """Clean up RecordReference rows when a WikiPage is deleted."""
    ct = ContentType.objects.get_for_model(sender)
    RecordReference.objects.filter(source_type=ct, source_id=instance.pk).delete()


@receiver(post_save, sender=WikiPage)
def ensure_page_has_tag(sender, instance, created, **kwargs):
    """Ensure every WikiPage has at least one WikiPageTag.

    If a page has no tags after being saved, create an untagged
    sentinel so the page appears in navigation and has a valid URL path.
    """
    if not instance.tags.exists():
        WikiPageTag.objects.create(
            page=instance,
            tag=UNTAGGED_SENTINEL,
            slug=instance.slug,
        )


@receiver(post_save, sender=WikiPageTag)
def remove_sentinel_when_tagged(sender, instance, created, **kwargs):
    """Remove the untagged sentinel when a real tag is added.

    When a page gets a non-empty tag, the empty sentinel is no longer
    needed and should be removed to avoid the page appearing both at
    root level and in its tag folder.
    """
    if created and instance.tag:
        # A non-empty tag was added; delete the sentinel if it exists
        WikiPageTag.objects.filter(page=instance.page, tag=UNTAGGED_SENTINEL).delete()
