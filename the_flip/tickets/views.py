import base64
from datetime import timedelta
from io import BytesIO
import os

import qrcode
import qrcode.image.svg
from PIL import Image

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.core.validators import validate_ipv46_address
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import GameFilterForm, ProblemReportCreateForm, ReportFilterForm, LogEntryForm, TaskCreateForm, LogWorkForm, MachineTaskFilterForm
from .models import MachineInstance, Task, LogEntry


def _get_request_ip(request):
    """Return the best-guess client IP, honoring common proxy headers."""
    header_ip = request.META.get('HTTP_X_FORWARDED_FOR')
    if header_ip:
        # X-Forwarded-For can contain multiple IPs. First value is the original client.
        candidate = header_ip.split(',')[0].strip()
    else:
        candidate = request.META.get('REMOTE_ADDR', '')

    if not candidate:
        return None

    try:
        validate_ipv46_address(candidate)
    except ValidationError:
        return None
    return candidate


def _report_submission_rate_limit_exceeded(ip_address: str | None) -> bool:
    """Return True if this client IP has exceeded the problem-report submission rate."""
    if not ip_address:
        return False

    max_reports = getattr(settings, 'REPORT_SUBMISSION_RATE_LIMIT_MAX', 5)
    window_seconds = getattr(settings, 'REPORT_SUBMISSION_RATE_LIMIT_WINDOW_SECONDS', 10 * 60)

    if max_reports <= 0 or window_seconds <= 0:
        return False

    cache_key = f'report-rate:{ip_address}'
    now = timezone.now()
    entry = cache.get(cache_key)

    if entry:
        reset_at = entry.get('reset_at')
        if not reset_at or reset_at <= now:
            entry = None
        else:
            count = entry.get('count', 0)
            if count >= max_reports:
                return True
            entry['count'] = count + 1
            remaining = max(int((reset_at - now).total_seconds()), 0)
            cache.set(cache_key, entry, timeout=remaining)
            return False

    reset_at = now + timedelta(seconds=window_seconds)
    cache.set(cache_key, {'count': 1, 'reset_at': reset_at}, timeout=window_seconds)
    return False


def home(request):
    """Redirect to task list."""
    return redirect('task_list')


class CustomLoginView(LoginView):
    """Custom login view with our template."""
    template_name = 'tickets/login.html'
    redirect_authenticated_user = True


def report_list(request):
    """
    Display list of problem reports with filtering.
    Accessible to everyone (public + maintainers).
    """
    reports = Task.objects.all().select_related('machine__model').order_by('-created_at')

    # Default to showing open reports when no status filter is provided
    query_params = request.GET.copy()
    if not query_params.get('status'):
        query_params = query_params.copy()
        query_params['status'] = Task.STATUS_OPEN

    form = ReportFilterForm(query_params or None)

    if form.is_valid():
        # Status filter
        status = form.cleaned_data.get('status')
        if status and status != 'all':
            reports = reports.filter(status=status)

        # Type filter
        type_filter = form.cleaned_data.get('type')
        if type_filter and type_filter != 'all':
            reports = reports.filter(type=type_filter)

        # Problem type filter
        problem_type = form.cleaned_data.get('problem_type')
        if problem_type and problem_type != 'all':
            reports = reports.filter(problem_type=problem_type)

        # Machine filter
        machine = form.cleaned_data.get('machine')
        if machine:
            reports = reports.filter(machine=machine)

        # Search filter
        search = form.cleaned_data.get('search')
        if search:
            reports = reports.filter(
                Q(problem_text__icontains=search) |
                Q(reported_by_name__icontains=search) |
                Q(machine__name_override__icontains=search) |
                Q(machine__model__name__icontains=search)
            )

    # Calculate stats
    stats = {
        'open_count': Task.objects.filter(status=Task.STATUS_OPEN).count(),
        'closed_count': Task.objects.filter(status=Task.STATUS_CLOSED).count(),
    }

    # Pagination
    paginator = Paginator(reports, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'tickets/report_list.html', {
        'page_obj': page_obj,
        'form': form,
        'stats': stats,
    })


def report_detail(request, pk):
    """
    Display single report with all updates.
    Everyone can view, but only authenticated maintainers can add updates.
    """
    report = get_object_or_404(
        Task.objects.select_related('machine__model').prefetch_related(
            'log_entries__maintainers__user'
        ),
        pk=pk
    )

    # Check if user can update (staff users or maintainers)
    can_update = request.user.is_authenticated and (
        request.user.is_staff or hasattr(request.user, 'maintainer')
    )

    form = None

    # Handle POST requests (staff or maintainers)
    if request.method == 'POST' and can_update:
        # Get maintainer object (None for staff users without maintainer record)
        maintainer = getattr(request.user, 'maintainer', None)
        maintainers = [maintainer] if maintainer else []

        if 'add_update' in request.POST:
            form = LogEntryForm(request.POST, current_machine_status=report.machine.operational_status)
            if form.is_valid():
                text = form.cleaned_data['text']
                machine_status = form.cleaned_data.get('machine_status')

                # If machine status was changed, use set_machine_status
                if machine_status:
                    report.set_machine_status(machine_status, maintainers, text)
                    messages.success(request, f'Update added and machine status changed to {dict(MachineInstance.OPERATIONAL_STATUS_CHOICES)[machine_status]}.')
                else:
                    # No machine status change, just add a note
                    report.add_note(maintainers, text)
                    messages.success(request, 'Update added successfully.')
                return redirect('task_detail', pk=pk)

    # Create empty form for GET requests or failed POST
    if can_update and form is None:
        form = LogEntryForm(current_machine_status=report.machine.operational_status)

    return render(request, 'tickets/report_detail.html', {
        'report': report,
        'form': form,
        'can_update': can_update,
    })


def problem_report_create(request, slug):
    """
    Visitor-facing problem report form (public access).

    Machine is pre-selected from the URL slug.
    This is the simplified interface accessed via QR codes at /p/<slug>/.
    """
    machine = get_object_or_404(
        MachineInstance.objects.exclude(operational_status=MachineInstance.OPERATIONAL_STATUS_BROKEN),
        slug=slug
    )

    if request.method == 'POST':
        form = ProblemReportCreateForm(request.POST, machine=machine, user=request.user)
        if form.is_valid():
            ip_address = _get_request_ip(request)
            if _report_submission_rate_limit_exceeded(ip_address):
                form.add_error(None, 'Too many problem reports from this device. Please wait a few minutes and try again.')
            else:
                report = form.save(commit=False)

                # Associate authenticated user if logged in
                if request.user.is_authenticated:
                    report.reported_by_user = request.user
                    report.reported_by_name = request.user.get_full_name() or request.user.username
                    if hasattr(request.user, 'maintainer'):
                        report.reported_by_contact = request.user.email
                else:
                    # Only capture device info for unauthenticated users
                    user_agent = request.META.get('HTTP_USER_AGENT', '')
                    report.device_info = f"{user_agent[:200]}"  # Limit to 200 chars
                    report.ip_address = ip_address

                report.save()

                messages.success(request, 'Problem report submitted successfully. Thank you!')
                return redirect('task_detail', pk=report.pk)
    else:
        form = ProblemReportCreateForm(machine=machine, user=request.user)

    return render(request, 'tickets/report_create.html', {
        'form': form,
        'machine': machine,
    })


@login_required
def task_create_todo(request):
    """
    Create a new TODO task (maintainers only).
    This is different from problem reports - it's for maintainer-created tasks.
    """
    # Check permission (staff users or maintainers)
    if not (request.user.is_staff or hasattr(request.user, 'maintainer')):
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('task_list')

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

    return render(request, 'tickets/task_create_todo.html', {
        'form': form,
    })


@login_required
def machine_log_create(request, slug):
    """
    Create a standalone work log entry for a machine (maintainers only).
    This is for recording work done that's not tied to a specific task/problem report.
    """
    # Check permission (staff users or maintainers)
    if not (request.user.is_staff or hasattr(request.user, 'maintainer')):
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('task_list')

    machine = get_object_or_404(MachineInstance, slug=slug)

    if request.method == 'POST':
        form = LogWorkForm(request.POST, machine=machine)
        if form.is_valid():
            log_entry = form.save(commit=False)
            # Standalone work logs have no associated task but must have machine
            log_entry.task = None
            log_entry.machine = machine
            log_entry.save()

            # Get maintainer object (None for staff users without maintainer record)
            maintainer = getattr(request.user, 'maintainer', None)
            if maintainer:
                log_entry.maintainers.add(maintainer)

            # Update machine status if provided
            machine_status = form.cleaned_data.get('machine_status')
            if machine_status:
                log_entry.machine_status = machine_status
                machine.operational_status = machine_status
                machine.save(update_fields=['operational_status'])
                log_entry.save(update_fields=['machine_status'])
                messages.success(request, f'Work logged and machine status updated to {dict(MachineInstance.OPERATIONAL_STATUS_CHOICES)[machine_status]}.')
            else:
                messages.success(request, 'Work logged successfully.')

            return redirect('machine_detail', slug=machine.slug)
    else:
        form = LogWorkForm(machine=machine)

    return render(request, 'tickets/log_work.html', {
        'form': form,
        'machine': machine,
    })


@login_required
def machine_list(request):
    """
    Display list of all machine instances.
    Only accessible to authenticated staff and maintainers.
    """
    # Check permission (staff users or maintainers)
    if not (request.user.is_staff or hasattr(request.user, 'maintainer')):
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('task_list')

    machines = MachineInstance.objects.all().select_related('model').order_by('model__name', 'serial_number')

    form = GameFilterForm(request.GET or None)

    if form.is_valid():
        # Search functionality
        search = form.cleaned_data.get('search')
        if search:
            machines = machines.filter(
                Q(name_override__icontains=search) |
                Q(model__name__icontains=search) |
                Q(model__manufacturer__icontains=search) |
                Q(serial_number__icontains=search)
            )

        # Filter by era
        era = form.cleaned_data.get('era')
        if era:
            machines = machines.filter(model__era=era)

        # Filter by location
        location = form.cleaned_data.get('location')
        if location:
            machines = machines.filter(location=location)

        # Filter by operational status
        operational_status = form.cleaned_data.get('operational_status')
        if operational_status:
            machines = machines.filter(operational_status=operational_status)

    # Pagination
    paginator = Paginator(machines, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'tickets/machine_list.html', {
        'page_obj': page_obj,
        'form': form,
    })


@login_required
def machine_detail(request, slug):
    """
    Display machine details with problem reports, tasks, and work logs.
    Only accessible to authenticated staff and maintainers.
    """
    # Check permission (staff users or maintainers)
    if not (request.user.is_staff or hasattr(request.user, 'maintainer')):
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('task_list')

    machine = get_object_or_404(MachineInstance.objects.select_related('model'), slug=slug)

    # Get recent tasks and problem reports (merged)
    recent_tasks = Task.objects.filter(
        machine=machine
    ).order_by('-created_at')[:5]

    # Get recent work logs for this machine
    recent_logs = LogEntry.objects.filter(
        machine=machine
    ).prefetch_related('maintainers__user').order_by('-created_at')[:5]

    return render(request, 'tickets/machine_detail.html', {
        'machine': machine,
        'recent_tasks': recent_tasks,
        'recent_logs': recent_logs,
    })


@login_required
def machine_tasks_list(request, slug):
    """
    List all tasks and problem reports for a specific machine (maintainers only).
    Supports filtering by type (all/problem reports/tasks) and status (all/open/closed).
    """
    # Check permission (staff users or maintainers)
    if not (request.user.is_staff or hasattr(request.user, 'maintainer')):
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('task_list')

    machine = get_object_or_404(MachineInstance.objects.select_related('model'), slug=slug)

    # Initialize the filter form with GET data
    form = MachineTaskFilterForm(request.GET or None)

    # Start with all tasks for this machine
    tasks = Task.objects.filter(machine=machine).order_by('-created_at')

    # Apply filters if form is valid
    if form.is_valid():
        filter_type = form.cleaned_data.get('type', 'all')
        filter_status = form.cleaned_data.get('status', 'all')

        # Apply type filter
        if filter_type == 'problem_report':
            tasks = tasks.filter(type=Task.TYPE_PROBLEM_REPORT)
        elif filter_type == 'task':
            tasks = tasks.filter(type=Task.TYPE_TASK)

        # Apply status filter
        if filter_status == 'open':
            tasks = tasks.filter(status=Task.STATUS_OPEN)
        elif filter_status == 'closed':
            tasks = tasks.filter(status=Task.STATUS_CLOSED)

    # Pagination
    paginator = Paginator(tasks, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'tickets/machine_tasks_list.html', {
        'machine': machine,
        'page_obj': page_obj,
        'form': form,
    })


@login_required
def machine_task_create(request, slug):
    """
    Create a new task or problem report for a specific machine (maintainers only).
    Machine is pre-selected from URL. Defaults to task type.
    """
    # Check permission (staff users or maintainers)
    if not (request.user.is_staff or hasattr(request.user, 'maintainer')):
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('task_list')

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

    # Hide the machine field since it's determined by the URL
    form.fields['machine'].widget = forms.HiddenInput()

    return render(request, 'tickets/machine_task_create.html', {
        'form': form,
        'machine': machine,
    })


@login_required
def machine_log_list(request, slug):
    """
    List all work log entries for a specific machine (maintainers only).
    Shows standalone logs and task-related logs.
    """
    # Check permission (staff users or maintainers)
    if not (request.user.is_staff or hasattr(request.user, 'maintainer')):
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('task_list')

    machine = get_object_or_404(MachineInstance.objects.select_related('model'), slug=slug)

    # Get all logs for this machine (both standalone and task-related)
    logs = LogEntry.objects.filter(
        machine=machine
    ).prefetch_related('maintainers__user', 'task').order_by('-created_at')

    # Pagination
    paginator = Paginator(logs, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'tickets/machine_log_list.html', {
        'machine': machine,
        'page_obj': page_obj,
    })


@login_required
def machine_log_detail(request, slug, pk):
    """
    Display details of a single log entry (maintainers only).
    """
    # Check permission (staff users or maintainers)
    if not (request.user.is_staff or hasattr(request.user, 'maintainer')):
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('task_list')

    machine = get_object_or_404(MachineInstance.objects.select_related('model'), slug=slug)

    # Get the log entry and verify it belongs to this machine
    log_entry = get_object_or_404(
        LogEntry.objects.prefetch_related('maintainers__user').select_related('task', 'machine'),
        pk=pk,
        machine=machine
    )

    return render(request, 'tickets/machine_log_detail.html', {
        'machine': machine,
        'log_entry': log_entry,
    })


def machine_public_view(request, slug):
    """
    Public-facing educational page for a machine.
    Displays educational content with option to report problems.
    No authentication required - accessible via QR codes.
    """
    instance = get_object_or_404(MachineInstance, slug=slug)

    return render(request, 'tickets/machine_public.html', {
        'instance': instance,
    })


@login_required
def machine_qr(request, slug):
    """
    Display QR code for a machine (print-optimized page).
    Only accessible to authenticated staff and maintainers.
    """
    # Check permission (staff users or maintainers)
    if not (request.user.is_staff or hasattr(request.user, 'maintainer')):
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('task_list')

    machine = get_object_or_404(MachineInstance, slug=slug)

    # Generate QR code
    # The QR code will link to the public educational page for this machine
    qr_url = request.build_absolute_uri(
        reverse('machine_public', args=[machine.slug])
    )

    # Create QR code with high error correction to allow logo embedding
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,  # High error correction (30%)
        box_size=10,
        border=4,
    )
    qr.add_data(qr_url)
    qr.make(fit=True)

    # Create QR code image
    img = qr.make_image(fill_color="black", back_color="white").convert('RGB')

    # Embed logo in the center of QR code
    logo_path = os.path.join(settings.BASE_DIR, 'tickets', 'static', 'tickets', 'images', 'the_flip_logo.png')
    if os.path.exists(logo_path):
        try:
            # Open and resize logo
            logo = Image.open(logo_path)

            # Calculate logo size (20% of QR code size)
            qr_width, qr_height = img.size
            logo_size = int(qr_width * 0.20)

            # Resize logo while maintaining aspect ratio
            logo.thumbnail((logo_size, logo_size), Image.Resampling.LANCZOS)

            # Create white background square slightly larger than logo
            logo_bg_size = int(logo_size * 1.1)
            logo_bg = Image.new('RGB', (logo_bg_size, logo_bg_size), 'white')

            # Calculate position to center the logo background
            logo_bg_pos = ((qr_width - logo_bg_size) // 2, (qr_height - logo_bg_size) // 2)

            # Paste white background
            img.paste(logo_bg, logo_bg_pos)

            # Calculate position to center the logo
            logo_pos = ((qr_width - logo.width) // 2, (qr_height - logo.height) // 2)

            # Paste logo (with transparency if available)
            if logo.mode == 'RGBA':
                img.paste(logo, logo_pos, logo)
            else:
                img.paste(logo, logo_pos)
        except Exception as e:
            # If logo embedding fails, continue with QR code without logo
            pass

    # Convert to base64 for embedding in HTML
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    img_str = base64.b64encode(buffer.getvalue()).decode()

    return render(request, 'tickets/machine_qr.html', {
        'machine': machine,
        'qr_code_data': img_str,
        'qr_url': qr_url,
    })
