"""Wiki signals: tag sentinel management."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UNTAGGED_SENTINEL, WikiPage, WikiPageTag


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
