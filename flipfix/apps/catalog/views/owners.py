"""Views for machine owner management."""

from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from flipfix.apps.catalog.forms import OwnerCommentForm, OwnerDocumentForm, OwnerForm
from flipfix.apps.catalog.models import Owner, OwnerDocument
from flipfix.apps.core.sort import article_sort_key


class OwnerListView(ListView):
    """List all machine owners with machine counts."""

    template_name = "catalog/owner_list.html"
    context_object_name = "owners"

    def get_queryset(self):
        return Owner.objects.annotate(
            machine_count=Count("machines"),
            sort_name=article_sort_key("name"),
        ).order_by("sort_name")


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
        context["machines"] = (
            self.object.machines.select_related("model", "location")
            .order_by("model__sort_name")
        )
        context["documents"] = self.object.documents.all()
        context["document_form"] = OwnerDocumentForm()
        context["comments"] = self.object.comments.select_related("posted_by").all()
        context["comment_form"] = OwnerCommentForm()
        return context

    def post(self, request, *args, **kwargs):
        """Handle document upload, delete, and comment actions."""
        self.object = self.get_object()
        action = request.POST.get("action", "")

        if action == "upload_document":
            return self._handle_upload(request)
        elif action == "delete_document":
            return self._handle_delete(request)
        elif action == "add_comment":
            return self._handle_comment(request)

        return redirect("owner-detail", slug=self.object.slug)

    def _handle_upload(self, request):
        form = OwnerDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            doc = form.save(commit=False)
            doc.owner = self.object
            doc.uploaded_by = request.user
            doc.save()
            messages.success(request, f"Document '{doc.display_name}' uploaded.")
        else:
            for error in form.errors.values():
                messages.error(request, error[0])
        return redirect("owner-detail", slug=self.object.slug)

    def _handle_delete(self, request):
        doc_id = request.POST.get("document_id")
        doc = get_object_or_404(OwnerDocument, pk=doc_id, owner=self.object)
        name = doc.display_name
        doc.file.delete(save=False)
        doc.delete()
        messages.success(request, f"Document '{name}' deleted.")
        return redirect("owner-detail", slug=self.object.slug)

    def _handle_comment(self, request):
        form = OwnerCommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.owner = self.object
            comment.posted_by = request.user
            comment.save()
            messages.success(request, "Comment added.")
        else:
            for error in form.errors.values():
                messages.error(request, error[0])
        return redirect("owner-detail", slug=self.object.slug)


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
