"""Views for machine owner management."""

from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Count
from django.urls import reverse
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from flipfix.apps.catalog.forms import OwnerForm
from flipfix.apps.catalog.models import Owner


class OwnerListView(ListView):
    """List all machine owners with machine counts."""

    template_name = "catalog/owner_list.html"
    context_object_name = "owners"

    def get_queryset(self):
        return Owner.objects.annotate(machine_count=Count("machines")).order_by("name")


class OwnerDetailView(DetailView):
    """Detail page for an owner: info, linked machines, documents, comments."""

    template_name = "catalog/owner_detail.html"
    model = Owner
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        return Owner.objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["machines"] = self.object.machines.select_related("model", "location").order_by(
            "model__name"
        )
        return context


class OwnerCreateView(SuccessMessageMixin, CreateView):
    """Create a new machine owner."""

    template_name = "catalog/owner_form.html"
    model = Owner
    form_class = OwnerForm
    success_message = "Owner '%(name)s' created."

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("owner-detail", kwargs={"slug": self.object.slug})


class OwnerUpdateView(SuccessMessageMixin, UpdateView):
    """Edit an existing owner."""

    template_name = "catalog/owner_form.html"
    model = Owner
    form_class = OwnerForm
    slug_field = "slug"
    slug_url_kwarg = "slug"
    success_message = "Owner '%(name)s' saved."

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("owner-detail", kwargs={"slug": self.object.slug})
