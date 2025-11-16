from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import ListView, TemplateView, FormView

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.catalog.models import MachineInstance
from the_flip.apps.maintenance.forms import LogEntryQuickForm, ProblemReportForm
from the_flip.apps.maintenance.models import LogEntry, LogEntryMedia, ProblemReport


class MaintenanceIndexView(TemplateView):
    template_name = "maintenance/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["open_reports"] = ProblemReport.objects.open().select_related("machine").order_by("-created_at")
        context["recent_logs"] = LogEntry.objects.select_related("machine").prefetch_related("maintainers")[:10]
        return context


class ProblemReportListView(ListView):
    template_name = "maintenance/problem_report_list.html"
    context_object_name = "reports"
    queryset = ProblemReport.objects.select_related("machine").order_by("-created_at")


class ProblemReportCreateView(FormView):
    template_name = "maintenance/problem_report_form.html"
    form_class = ProblemReportForm

    def dispatch(self, request, *args, **kwargs):
        self.machine = get_object_or_404(MachineInstance, slug=kwargs["slug"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["machine"] = self.machine
        return context

    def form_valid(self, form):
        report = form.save(commit=False)
        report.machine = self.machine
        report.ip_address = self.request.META.get("REMOTE_ADDR")
        report.save()
        messages.success(self.request, "Thanks! The maintenance team has been notified.")
        return redirect(self.machine.get_absolute_url())


class MachineLogView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = "maintenance/machine_log.html"

    def test_func(self):
        return self.request.user.is_staff

    def dispatch(self, request, *args, **kwargs):
        self.machine = get_object_or_404(MachineInstance, slug=kwargs["slug"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        logs = (
            LogEntry.objects.filter(machine=self.machine)
            .select_related("machine")
            .prefetch_related("maintainers", "media")
            .order_by("-created_at")
        )
        paginator = Paginator(logs, 10)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        context.update(
            {
                "machine": self.machine,
                "page_obj": page_obj,
                "log_entries": page_obj.object_list,
            }
        )
        return context


class MachineLogCreateView(LoginRequiredMixin, UserPassesTestMixin, FormView):
    template_name = "maintenance/machine_log_new.html"
    form_class = LogEntryQuickForm

    def test_func(self):
        return self.request.user.is_staff

    def dispatch(self, request, *args, **kwargs):
        self.machine = get_object_or_404(MachineInstance, slug=kwargs["slug"])
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        if self.request.user.is_authenticated:
            initial["submitter_name"] = (
                self.request.user.get_full_name() or self.request.user.get_username()
            )
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["machine"] = self.machine
        return context

    def form_valid(self, form):
        submitter_name = form.cleaned_data["submitter_name"].strip()
        description = form.cleaned_data["text"].strip()
        photo = form.cleaned_data["photo"]
        log_entry = LogEntry.objects.create(machine=self.machine, text=description)

        maintainer = self.match_maintainer(submitter_name)
        if maintainer:
            log_entry.maintainers.add(maintainer)
        elif submitter_name:
            log_entry.maintainer_names = submitter_name
            log_entry.save(update_fields=["maintainer_names"])

        if photo:
            LogEntryMedia.objects.create(
                log_entry=log_entry,
                media_type=LogEntryMedia.TYPE_PHOTO,
                file=photo,
            )

        messages.success(self.request, "Log entry recorded.")
        return redirect("maintenance:machine-log", slug=self.machine.slug)

    def match_maintainer(self, name: str):
        normalized = name.lower().strip()
        if not normalized:
            return None
        for maintainer in Maintainer.objects.select_related("user"):
            username = maintainer.user.username.lower()
            full_name = (maintainer.user.get_full_name() or "").lower()
            if normalized in {username, full_name}:
                return maintainer
        return None
