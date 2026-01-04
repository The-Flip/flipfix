"""Home page views."""

from constance import config
from django.views import View
from django.views.generic import TemplateView

from the_flip.apps.core.mixins import can_access_maintainer_portal
from the_flip.apps.core.views.feed import GlobalActivityFeedView


class HomeView(View):
    """Home page: activity feed for maintainers, welcome page for others."""

    def get(self, request):
        if (
            config.GLOBAL_ACTIVITY_FEED_ENABLED
            and request.user.is_authenticated
            and can_access_maintainer_portal(request.user)
        ):
            return GlobalActivityFeedView.as_view()(request)
        return PublicHomeView.as_view()(request)


class PublicHomeView(TemplateView):
    """Public landing page for logged-out users or non-maintainers."""

    template_name = "home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Check if current user is a shared account
        is_shared_account = False
        if self.request.user.is_authenticated and hasattr(self.request.user, "maintainer"):
            is_shared_account = self.request.user.maintainer.is_shared_account
        context["is_shared_account"] = is_shared_account
        return context
