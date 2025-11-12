"""Views focused on machine management workflows."""

from __future__ import annotations

import base64
import os
from io import BytesIO

import qrcode
import qrcode.image.svg  # noqa: F401  # Imported for potential future use
from PIL import Image

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from ..decorators import maintainer_required
from ..forms import (
    GameFilterForm,
    LogWorkForm,
    MachineLogFilterForm,
    MachineTaskFilterForm,
    QuickTaskCreateForm,
    TaskCreateForm,
)
from ..models import LogEntry, MachineInstance, Task


@login_required
@maintainer_required
def machine_log_create(request, slug):
    """Create a standalone work log entry for a machine."""

    machine = get_object_or_404(MachineInstance, slug=slug)

    if request.method == 'POST':
        form = LogWorkForm(request.POST, machine=machine)
        if form.is_valid():
            log_entry = form.save(commit=False)
            log_entry.task = None
            log_entry.machine = machine
            log_entry.save()

            maintainer = getattr(request.user, 'maintainer', None)
            if maintainer:
                log_entry.maintainers.add(maintainer)

            machine_status = form.cleaned_data.get('machine_status')
            if machine_status:
                log_entry.machine_status = machine_status
                machine.operational_status = machine_status
                machine.save(update_fields=['operational_status'])
                log_entry.save(update_fields=['machine_status'])
                messages.success(
                    request,
                    f"Work logged and machine status updated to {dict(MachineInstance.OPERATIONAL_STATUS_CHOICES)[machine_status]}.",
                )
            else:
                messages.success(request, 'Work logged successfully.')

            return redirect('machine_detail', slug=machine.slug)
    else:
        form = LogWorkForm(machine=machine)

    return render(
        request,
        'tickets/log_work.html',
        {
            'form': form,
            'machine': machine,
        },
    )


@login_required
@maintainer_required
def machine_list(request):
    """List all machine instances for maintainers."""

    machines = MachineInstance.objects.all().select_related('model').order_by('model__name', 'serial_number')

    form = GameFilterForm(request.GET or None)

    if form.is_valid():
        search = form.cleaned_data.get('search')
        if search:
            machines = machines.filter(
                Q(name_override__icontains=search)
                | Q(model__name__icontains=search)
                | Q(model__manufacturer__icontains=search)
                | Q(serial_number__icontains=search)
            )

        era = form.cleaned_data.get('era')
        if era:
            machines = machines.filter(model__era=era)

        location = form.cleaned_data.get('location')
        if location:
            machines = machines.filter(location=location)

        operational_status = form.cleaned_data.get('operational_status')
        if operational_status:
            machines = machines.filter(operational_status=operational_status)

    paginator = Paginator(machines, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        'tickets/machine_list.html',
        {
            'page_obj': page_obj,
            'form': form,
        },
    )


@login_required
@maintainer_required
def machine_detail(request, slug):
    """Display a single machine with task/log context."""

    machine = get_object_or_404(MachineInstance.objects.select_related('model'), slug=slug)

    if request.method == 'POST':
        quick_form = QuickTaskCreateForm(request.POST)
        if quick_form.is_valid():
            task = quick_form.save(commit=False)
            task.machine = machine
            task.reported_by_user = request.user
            task.reported_by_name = request.user.get_full_name() or request.user.username
            task.save()
            messages.success(request, 'Task created successfully.')
            return redirect('machine_detail', slug=machine.slug)
    else:
        quick_form = QuickTaskCreateForm()

    # Show only open tasks and problem reports, ordered chronologically (oldest first, like messages)
    tasks = Task.objects.filter(
        machine=machine,
        status=Task.STATUS_OPEN
    ).order_by('created_at')

    return render(
        request,
        'tickets/machine_detail.html',
        {
            'machine': machine,
            'tasks': tasks,
            'quick_form': quick_form,
        },
    )


@login_required
@maintainer_required
def machine_tasks_list(request, slug):
    """List all tasks/problem reports for a machine (v1 UI)."""

    machine = get_object_or_404(MachineInstance.objects.select_related('model'), slug=slug)

    if request.method == 'POST':
        quick_form = QuickTaskCreateForm(request.POST)
        if quick_form.is_valid():
            task = quick_form.save(commit=False)
            task.machine = machine
            task.reported_by_user = request.user
            task.reported_by_name = request.user.get_full_name() or request.user.username
            task.save()
            messages.success(request, 'Task created successfully.')
            return redirect('machine_tasks_list', slug=machine.slug)
    else:
        quick_form = QuickTaskCreateForm()

    form = MachineTaskFilterForm(request.GET or None)
    tasks = Task.objects.filter(machine=machine).order_by('-created_at')

    if form.is_valid():
        filter_type = form.cleaned_data.get('type', 'all')
        filter_status = form.cleaned_data.get('status', 'all')

        if filter_type == 'problem_report':
            tasks = tasks.filter(type=Task.TYPE_PROBLEM_REPORT)
        elif filter_type == 'task':
            tasks = tasks.filter(type=Task.TYPE_TASK)

        if filter_status == 'open':
            tasks = tasks.filter(status=Task.STATUS_OPEN)
        elif filter_status == 'closed':
            tasks = tasks.filter(status=Task.STATUS_CLOSED)

        search = form.cleaned_data.get('search')
        if search:
            tasks = tasks.filter(
                Q(problem_text__icontains=search)
                | Q(log_entries__text__icontains=search)
            ).distinct()

    paginator = Paginator(tasks, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        'tickets/machine_tasks_list.html',
        {
            'machine': machine,
            'page_obj': page_obj,
            'form': form,
            'quick_form': quick_form,
        },
    )


@login_required
@maintainer_required
def machine_task_create(request, slug):
    """Create a new task or problem report scoped to a machine."""

    machine = get_object_or_404(MachineInstance, slug=slug)

    if request.method == 'POST':
        form = TaskCreateForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.machine = machine
            task.reported_by_user = request.user
            task.reported_by_name = request.user.get_full_name() or request.user.username
            task.save()

            messages.success(request, 'Task created successfully.')
            return redirect('task_detail', pk=task.pk)
    else:
        form = TaskCreateForm(initial={'machine': machine})

    form.fields['machine'].widget = forms.HiddenInput()

    return render(
        request,
        'tickets/machine_task_create.html',
        {
            'form': form,
            'machine': machine,
        },
    )


@login_required
@maintainer_required
def machine_tasks_list_v2(request, slug):
    """Experimental task/problem report list for a machine (v2 UI)."""

    machine = get_object_or_404(MachineInstance.objects.select_related('model'), slug=slug)

    if request.method == 'POST':
        quick_form = QuickTaskCreateForm(request.POST)
        if quick_form.is_valid():
            task = quick_form.save(commit=False)
            task.machine = machine
            task.reported_by_user = request.user
            task.reported_by_name = request.user.get_full_name() or request.user.username
            task.save()
            messages.success(request, 'Task created successfully.')
            return redirect('machine_tasks_list_v2', slug=machine.slug)
    else:
        quick_form = QuickTaskCreateForm()

    # Show only open tasks and problem reports, ordered chronologically (oldest first, like messages)
    tasks = Task.objects.filter(
        machine=machine,
        status=Task.STATUS_OPEN
    ).order_by('created_at')

    return render(
        request,
        'tickets/machine_tasks_list_v2.html',
        {
            'machine': machine,
            'tasks': tasks,
            'quick_form': quick_form,
        },
    )


@login_required
@maintainer_required
def machine_log_list(request, slug):
    """List work log entries for a machine."""

    machine = get_object_or_404(MachineInstance.objects.select_related('model'), slug=slug)

    logs = LogEntry.objects.filter(machine=machine).prefetch_related('maintainers__user', 'task')

    form = MachineLogFilterForm(request.GET or None)

    if form.is_valid():
        search = form.cleaned_data.get('search')
        if search:
            logs = logs.filter(
                Q(text__icontains=search) | Q(task__problem_text__icontains=search)
            )

    logs = logs.order_by('-created_at')

    paginator = Paginator(logs, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        'tickets/machine_log_list.html',
        {
            'machine': machine,
            'page_obj': page_obj,
            'form': form,
        },
    )


@login_required
@maintainer_required
def machine_log_detail(request, slug, pk):
    """Display a single log entry."""

    machine = get_object_or_404(MachineInstance.objects.select_related('model'), slug=slug)

    log_entry = get_object_or_404(
        LogEntry.objects.prefetch_related('maintainers__user').select_related('task', 'machine'),
        pk=pk,
        machine=machine,
    )

    return render(
        request,
        'tickets/machine_log_detail.html',
        {
            'machine': machine,
            'log_entry': log_entry,
        },
    )


def machine_public_view(request, slug):
    """Public educational page for a machine."""

    instance = get_object_or_404(MachineInstance, slug=slug)

    return render(
        request,
        'tickets/machine_public.html',
        {
            'instance': instance,
        },
    )


@login_required
@maintainer_required
def machine_qr(request, slug):
    """Render a printable QR code for the machine."""

    machine = get_object_or_404(MachineInstance, slug=slug)

    qr_url = request.build_absolute_uri(reverse('machine_public', args=[machine.slug]))

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color='black', back_color='white').convert('RGB')

    logo_path = os.path.join(settings.BASE_DIR, 'tickets', 'static', 'tickets', 'images', 'the_flip_logo.png')
    if os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path)

            qr_width, qr_height = img.size
            logo_size = int(qr_width * 0.20)

            logo.thumbnail((logo_size, logo_size), Image.Resampling.LANCZOS)

            logo_bg_size = int(logo_size * 1.1)
            logo_bg = Image.new('RGB', (logo_bg_size, logo_bg_size), 'white')
            logo_bg_pos = ((qr_width - logo_bg_size) // 2, (qr_height - logo_bg_size) // 2)
            img.paste(logo_bg, logo_bg_pos)

            logo_pos = ((qr_width - logo.width) // 2, (qr_height - logo.height) // 2)

            if logo.mode == 'RGBA':
                img.paste(logo, logo_pos, logo)
            else:
                img.paste(logo, logo_pos)
        except Exception:
            # Continue without the embedded logo on failure.
            pass

    buffer = BytesIO()
    img.save(buffer, format='PNG')
    img_str = base64.b64encode(buffer.getvalue()).decode()

    return render(
        request,
        'tickets/machine_qr.html',
        {
            'machine': machine,
            'qr_code_data': img_str,
            'qr_url': qr_url,
        },
    )

