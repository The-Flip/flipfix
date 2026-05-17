"""Tests for ``MaintainerActivityMiddleware``.

The middleware updates ``Maintainer.last_active_at`` at most once per 24h
per user, gated by Django's cache framework via ``cache.add(...)``. Tests
isolate the cache to a unique ``LocMemCache`` location per class so they
don't bleed into each other or into other test modules.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings, tag
from django.urls import reverse
from django.utils import timezone

from flipfix.apps.accounts.models import Maintainer
from flipfix.apps.core.test_utils import (
    create_maintainer_user,
    create_user,
)
from flipfix.middleware import MaintainerActivityMiddleware


def _isolated_cache(location: str) -> dict:
    """Return a CACHES override that points at a fresh per-class LocMemCache.

    Each ``LocMemCache`` instance is keyed by LOCATION, so giving every class
    a unique location prevents one class's cache state from leaking into
    another's. The classes' ``setUp`` methods additionally ``cache.clear()``
    to isolate test methods *within* a class — the unique LOCATION alone
    only isolates across classes.
    """
    return {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": location,
        }
    }


@tag("views")
@override_settings(CACHES=_isolated_cache("activity-middleware-basic"))
class MaintainerActivityMiddlewareBasicTests(TestCase):
    """First-touch behavior: an authenticated maintainer's first request bumps
    ``last_active_at`` and primes the cache gate."""

    def setUp(self):
        # ``@override_settings(CACHES=...)`` gives each class its own
        # LocMemCache LOCATION, but every test method within the class shares
        # that backend. Clear between methods so a prior test's cache entries
        # can't trip the once-per-day gate for a reused user_id.
        cache.clear()

    def test_first_request_sets_last_active_at(self):
        user = create_maintainer_user(username="alice")
        self.assertIsNone(user.maintainer.last_active_at)

        self.client.force_login(user)
        before = timezone.now()
        self.client.get(reverse("user-directory"))

        user.maintainer.refresh_from_db()
        self.assertIsNotNone(user.maintainer.last_active_at)
        # Within a generous window — middleware uses timezone.now() at the
        # moment of the touch, after the view runs.
        self.assertGreaterEqual(user.maintainer.last_active_at, before)

    def test_cache_key_is_set_after_request(self):
        user = create_maintainer_user(username="bob")
        self.client.force_login(user)
        self.client.get(reverse("user-directory"))

        key = MaintainerActivityMiddleware.CACHE_KEY_TEMPLATE.format(user_id=user.id)
        self.assertTrue(cache.get(key))


@tag("views")
@override_settings(CACHES=_isolated_cache("activity-middleware-gate"))
class MaintainerActivityMiddlewareGateTests(TestCase):
    """Once-per-day gate: while the cache key exists, ``last_active_at`` does
    not move. When the key is gone, the next request updates again."""

    def setUp(self):
        # See note in MaintainerActivityMiddlewareBasicTests.setUp.
        cache.clear()

    def test_second_request_within_window_does_not_update(self):
        user = create_maintainer_user(username="alice")
        self.client.force_login(user)

        # First request primes the cache and sets last_active_at.
        self.client.get(reverse("user-directory"))
        user.maintainer.refresh_from_db()
        first_seen = user.maintainer.last_active_at
        self.assertIsNotNone(first_seen)

        # Pin the stored timestamp into the past so we'd notice any new write.
        Maintainer.objects.filter(user=user).update(last_active_at=first_seen - timedelta(hours=1))

        # Second request inside the 24h cache window: cache.add returns False,
        # the .update() must be skipped.
        self.client.get(reverse("user-directory"))
        user.maintainer.refresh_from_db()
        self.assertEqual(user.maintainer.last_active_at, first_seen - timedelta(hours=1))

    def test_expired_cache_allows_next_request_to_update(self):
        user = create_maintainer_user(username="alice")
        self.client.force_login(user)
        self.client.get(reverse("user-directory"))

        # Simulate cache TTL expiry by deleting the key.
        key = MaintainerActivityMiddleware.CACHE_KEY_TEMPLATE.format(user_id=user.id)
        cache.delete(key)

        # Pin the timestamp backward; a fresh request should advance it.
        Maintainer.objects.filter(user=user).update(
            last_active_at=timezone.now() - timedelta(days=2)
        )
        before = timezone.now()
        self.client.get(reverse("user-directory"))

        user.maintainer.refresh_from_db()
        self.assertGreaterEqual(user.maintainer.last_active_at, before)


@tag("views")
@override_settings(CACHES=_isolated_cache("activity-middleware-noop"))
class MaintainerActivityMiddlewareNoOpTests(TestCase):
    """Cases that must produce no DB write."""

    def setUp(self):
        # See note in MaintainerActivityMiddlewareBasicTests.setUp.
        cache.clear()

    def test_anonymous_user_skips_db_and_cache(self):
        """``_touch`` is the no-op contract for anonymous users.

        Calling it directly (rather than through ``self.client.get(...)``)
        isolates the middleware from any incidental queries the request
        pipeline issues, so ``assertNumQueries(0)`` actually means
        "the middleware did not touch the database."
        """
        request = RequestFactory().get("/")
        request.user = AnonymousUser()
        middleware = MaintainerActivityMiddleware(lambda _r: HttpResponse())

        with self.assertNumQueries(0):
            middleware._touch(request)

        # AnonymousUser.id is None; even if the guard ever regressed and we
        # cached for that, the key would still be absent here.
        anon_key = MaintainerActivityMiddleware.CACHE_KEY_TEMPLATE.format(user_id=None)
        self.assertIsNone(cache.get(anon_key))

    def test_authenticated_user_without_maintainer_row_is_safe(self):
        """A logged-in user without a ``Maintainer`` profile must not crash
        the middleware. ``.filter().update()`` returns rowcount 0.

        We also assert the cache key got set — that proves ``_touch`` actually
        reached the no-op write path on the 403 response, rather than the
        ``not Maintainer.objects.filter(...).exists()`` assertion passing
        vacuously because the middleware was never invoked.
        """
        user = create_user(username="orphan")
        self.client.force_login(user)
        # /users/ 403s for this user via MaintainerAccessMiddleware.process_view.
        # The 403 response still flows back through every middleware __call__,
        # so MaintainerActivityMiddleware._touch runs on the response path —
        # the exact case we want to exercise.
        self.client.get(reverse("user-directory"))

        key = MaintainerActivityMiddleware.CACHE_KEY_TEMPLATE.format(user_id=user.id)
        self.assertTrue(cache.get(key), "_touch should have set the cache gate")
        self.assertFalse(Maintainer.objects.filter(user=user).exists())


@tag("views")
@override_settings(CACHES=_isolated_cache("activity-middleware-updated-at"))
class MaintainerActivityMiddlewareUpdatedAtTests(TestCase):
    """The activity write must use ``.update()``, not ``.save()``, so it
    doesn't bump ``TimeStampedMixin.updated_at`` (auto_now=True fires on save
    only). ``updated_at`` should reserve the meaning of "profile last edited."
    """

    def setUp(self):
        # See note in MaintainerActivityMiddlewareBasicTests.setUp.
        cache.clear()

    def test_activity_touch_does_not_bump_updated_at(self):
        user = create_maintainer_user(username="alice")
        original_updated_at = Maintainer.objects.get(user=user).updated_at

        self.client.force_login(user)
        self.client.get(reverse("user-directory"))

        refreshed = Maintainer.objects.get(user=user)
        self.assertIsNotNone(refreshed.last_active_at)
        self.assertEqual(refreshed.updated_at, original_updated_at)
