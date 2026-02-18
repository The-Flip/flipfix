"""Home page views."""

from django.contrib import messages
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import TemplateView, UpdateView

from flipfix.apps.core.forms import SiteSettingsForm
from flipfix.apps.core.mixins import SharedAccountMixin, can_access_maintainer_portal
from flipfix.apps.core.models import SiteSettings
from flipfix.apps.core.views.feed import GlobalActivityFeedView


class HomeView(View):
    """Home page: activity feed for maintainers, welcome page for others."""

    def get(self, request):
        if request.user.is_authenticated and can_access_maintainer_portal(request.user):
            return GlobalActivityFeedView.as_view()(request)
        return PublicHomeView.as_view()(request)


class PublicHomeView(SharedAccountMixin, TemplateView):
    """Public landing page for logged-out users or non-maintainers."""

    template_name = "home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["front_page_content"] = SiteSettings.load().front_page_content
        return context


class SiteSettingsEditView(UpdateView):
    """Superuser-only form for editing site-wide settings."""

    model = SiteSettings
    form_class = SiteSettingsForm
    template_name = "core/site_settings_form.html"
    success_url = reverse_lazy("site-settings")

    def get_object(self, queryset=None):
        return SiteSettings.load()

    def form_valid(self, form):
        messages.success(self.request, "Site settings saved.")
        return super().form_valid(form)
