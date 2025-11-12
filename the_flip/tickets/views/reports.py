"""Views that deal with global tasks and problem reports."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from ..decorators import maintainer_required
from ..forms import (
    LogEntryForm,
    ProblemReportCreateForm,
    ReportFilterForm,
    TaskCreateForm,
)
from ..models import MachineInstance, Task
from ..services.report_submission import (
    get_request_ip,
    report_submission_rate_limit_exceeded,
)


def report_list(request):
    """Display problem reports/tasks with filtering for everyone."""

    # Show only open tasks by default
    reports = Task.objects.filter(status=Task.STATUS_OPEN).select_related('machine__model').order_by('-created_at')

    form = ReportFilterForm(request.GET or None)

    if form.is_valid():
        type_filter = form.cleaned_data.get('type')
        if type_filter and type_filter != 'all':
            reports = reports.filter(type=type_filter)

        machine = form.cleaned_data.get('machine')
        if machine:
            reports = reports.filter(machine=machine)

        search = form.cleaned_data.get('search')
        if search:
            reports = reports.filter(
                Q(problem_text__icontains=search)
                | Q(reported_by_name__icontains=search)
                | Q(machine__name_override__icontains=search)
                | Q(machine__model__name__icontains=search)
                | Q(log_entries__text__icontains=search)
            ).distinct()

    stats = {
        'open_count': Task.objects.filter(status=Task.STATUS_OPEN).count(),
        'closed_count': Task.objects.filter(status=Task.STATUS_CLOSED).count(),
    }

    paginator = Paginator(reports, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        'tickets/report_list.html',
        {
            'page_obj': page_obj,
            'form': form,
            'stats': stats,
        },
    )


def report_detail(request, pk):
    """Display a single report with its updates."""

    report = get_object_or_404(
        Task.objects.select_related('machine__model').prefetch_related('log_entries__maintainers__user'),
        pk=pk,
    )

    can_update = request.user.is_authenticated and (
        request.user.is_staff or hasattr(request.user, 'maintainer')
    )

    form = None

    if request.method == 'POST' and can_update:
        maintainer = getattr(request.user, 'maintainer', None)
        maintainers = [maintainer] if maintainer else []

        if 'add_update' in request.POST:
            form = LogEntryForm(
                request.POST,
                current_machine_status=report.machine.operational_status,
                current_task_status=report.status
            )
            if form.is_valid():
                text = form.cleaned_data['text']
                machine_status = form.cleaned_data.get('machine_status')
                change_task_status = form.cleaned_data.get('change_task_status', False)

                # Handle task status change independently
                if change_task_status:
                    # Toggle task status
                    new_task_status = Task.STATUS_CLOSED if report.status == Task.STATUS_OPEN else Task.STATUS_OPEN
                    report.set_status(new_task_status, maintainers, text)
                    status_msg = f"Task {'closed' if new_task_status == Task.STATUS_CLOSED else 're-opened'}"
                elif machine_status:
                    # Machine status change (this will also update task status automatically via set_machine_status)
                    report.set_machine_status(machine_status, maintainers, text)
                    status_msg = f"Machine status changed to {dict(MachineInstance.OPERATIONAL_STATUS_CHOICES)[machine_status]}"
                else:
                    # Just a note
                    report.add_note(maintainers, text)
                    status_msg = "Update added"

                messages.success(request, f"{status_msg} successfully.")
                return redirect('task_detail', pk=pk)

    if can_update and form is None:
        form = LogEntryForm(
            current_machine_status=report.machine.operational_status,
            current_task_status=report.status
        )

    return render(
        request,
        'tickets/report_detail.html',
        {
            'report': report,
            'form': form,
            'can_update': can_update,
        },
    )


def problem_report_create(request, slug):
    """Visitor-facing problem report form with the machine bound via slug."""

    machine = get_object_or_404(
        MachineInstance.objects.exclude(operational_status=MachineInstance.OPERATIONAL_STATUS_BROKEN),
        slug=slug,
    )

    if request.method == 'POST':
        form = ProblemReportCreateForm(request.POST, machine=machine, user=request.user)
        if form.is_valid():
            ip_address = get_request_ip(request)
            if report_submission_rate_limit_exceeded(ip_address):
                form.add_error(
                    None,
                    'Too many problem reports from this device. Please wait a few minutes and try again.',
                )
            else:
                report = form.save(commit=False)

                if request.user.is_authenticated:
                    report.reported_by_user = request.user
                    report.reported_by_name = request.user.get_full_name() or request.user.username
                    if hasattr(request.user, 'maintainer'):
                        report.reported_by_contact = request.user.email
                else:
                    user_agent = request.META.get('HTTP_USER_AGENT', '')
                    report.device_info = f"{user_agent[:200]}"
                    report.ip_address = ip_address

                report.save()

                messages.success(request, 'Problem report submitted successfully. Thank you!')
                return redirect('machine_public', slug=machine.slug)
    else:
        form = ProblemReportCreateForm(machine=machine, user=request.user)

    return render(
        request,
        'tickets/report_create.html',
        {
            'form': form,
            'machine': machine,
        },
    )


@login_required
@maintainer_required
def task_create_todo(request):
    """Maintainer workflow for creating TODO tasks."""

    if request.method == 'POST':
        form = TaskCreateForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.reported_by_user = request.user
            task.reported_by_name = request.user.get_full_name() or request.user.username
            task.save()

            messages.success(request, 'Task created successfully.')
            return redirect('task_detail', pk=task.pk)
    else:
        form = TaskCreateForm()

    return render(
        request,
        'tickets/task_create_todo.html',
        {
            'form': form,
        },
    )

