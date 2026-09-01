"""The maintainer directory and the per-user profile pages."""

from django.core.exceptions import PermissionDenied
from django.db.models import F, Value
from django.db.models.functions import Coalesce, Lower, NullIf
from django.views.generic import DetailView, ListView

from ..models import Maintainer
from ..permissions import can_view_user_profiles


class UserProfileDetailView(DetailView):
    """Profile detail page at ``/users/<username>/``.

    Same access pattern as ``UserDirectoryView``: middleware gates to
    logged-in maintainers, ``dispatch()`` layers ``can_view_user_profiles``
    on top. The queryset is ``Maintainer.objects.in_user_directory()`` —
    single source of truth — so any maintainer who would not appear in the
    directory listing also 404s here.
    """

    template_name = "accounts/user_profile.html"
    context_object_name = "maintainer"
    slug_field = "user__username"
    slug_url_kwarg = "username"

    def dispatch(self, request, *args, **kwargs):
        if not can_view_user_profiles(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return (
            Maintainer.objects.in_user_directory().select_related("user").prefetch_related("media")
        )


class UserDirectoryView(ListView):
    """Public-to-maintainers directory of profile pages.

    Access: middleware gates this to logged-in maintainers (default
    ``access=None`` on the URL). ``dispatch()`` adds the extra
    ``can_view_user_profiles`` capability check on top — kept inline
    rather than via a mixin to mirror the per-view auth style in
    ``docs/Views.md``.
    """

    template_name = "accounts/user_directory.html"
    context_object_name = "maintainers"

    def dispatch(self, request, *args, **kwargs):
        if not can_view_user_profiles(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        # Primary sort: most recently active first, so volunteers who actually
        # use the system surface to the top and lapsed accounts drift down.
        # Never-seen maintainers (NULL last_active_at) fall to the bottom and
        # use the alphabetical tiebreaker.
        #
        # Tiebreaker: the same character users read — first name if set,
        # otherwise username. Lower() is required because Postgres and
        # SQLite default collations are byte-order, so without it "alice"
        # would sort after "Zoe". .distinct() is defensive against the
        # user__groups M2M join inside in_user_directory() — today a user
        # can only be in the Maintainers group once, but the join could
        # silently produce duplicates if the predicate evolves.
        sort_key = Lower(Coalesce(NullIf("user__first_name", Value("")), "user__username"))
        # prefetch_related("media") loads every MaintainerMedia row per
        # maintainer (≤10 each) although the card only renders the first.
        # Fine at expected scale (dozens of maintainers); if the directory
        # grows past a few hundred, switch to a Subquery for the first-id
        # or a sliced Prefetch with to_attr.
        return (
            Maintainer.objects.in_user_directory()
            .select_related("user")
            .prefetch_related("media")
            .order_by(F("last_active_at").desc(nulls_last=True), sort_key)
            .distinct()
        )
