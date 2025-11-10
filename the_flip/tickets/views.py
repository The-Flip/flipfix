import base64
from datetime import timedelta
from io import BytesIO
import os

import qrcode
import qrcode.image.svg
from PIL import Image

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

from .forms import GameFilterForm, ProblemReportCreateForm, ReportFilterForm, ReportUpdateForm
from .models import Game, ProblemReport


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
    """Redirect to report list."""
    return redirect('report_list')


class CustomLoginView(LoginView):
    """Custom login view with our template."""
    template_name = 'tickets/login.html'
    redirect_authenticated_user = True


def report_list(request):
    """
    Display list of problem reports with filtering.
    Accessible to everyone (public + maintainers).
    """
    reports = ProblemReport.objects.all().select_related('game').order_by('-created_at')

    # Default to showing open reports when no status filter is provided
    query_params = request.GET.copy()
    if not query_params.get('status'):
        query_params = query_params.copy()
        query_params['status'] = ProblemReport.STATUS_OPEN

    form = ReportFilterForm(query_params or None)

    if form.is_valid():
        # Status filter
        status = form.cleaned_data.get('status')
        if status and status != 'all':
            reports = reports.filter(status=status)

        # Problem type filter
        problem_type = form.cleaned_data.get('problem_type')
        if problem_type and problem_type != 'all':
            reports = reports.filter(problem_type=problem_type)

        # Game filter
        game = form.cleaned_data.get('game')
        if game:
            reports = reports.filter(game=game)

        # Search filter
        search = form.cleaned_data.get('search')
        if search:
            reports = reports.filter(
                Q(problem_text__icontains=search) |
                Q(reported_by_name__icontains=search)
            )

    # Calculate stats
    stats = {
        'open_count': ProblemReport.objects.filter(status=ProblemReport.STATUS_OPEN).count(),
        'closed_count': ProblemReport.objects.filter(status=ProblemReport.STATUS_CLOSED).count(),
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
        ProblemReport.objects.select_related('game').prefetch_related(
            'updates__maintainer__user'
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

        if 'add_update' in request.POST:
            form = ReportUpdateForm(request.POST, current_game_status=report.game.status)
            if form.is_valid():
                text = form.cleaned_data['text']
                game_status = form.cleaned_data.get('game_status')

                # If game status was changed, use set_game_status
                if game_status:
                    report.set_game_status(game_status, maintainer, text)
                    messages.success(request, f'Update added and game status changed to {dict(Game.STATUS_CHOICES)[game_status]}.')
                else:
                    # No game status change, just add a note
                    report.add_note(maintainer, text)
                    messages.success(request, 'Update added successfully.')
                return redirect('report_detail', pk=pk)

    # Create empty form for GET requests or failed POST
    if can_update and form is None:
        form = ReportUpdateForm(current_game_status=report.game.status)

    return render(request, 'tickets/report_detail.html', {
        'report': report,
        'form': form,
        'can_update': can_update,
    })


def report_create(request, game_id=None):
    """
    Create a new problem report.

    If game_id is provided (QR code scenario), the game is pre-selected.
    Otherwise, user selects from dropdown.

    Accessible to everyone (public + maintainers).
    """
    game = None
    if game_id:
        game = get_object_or_404(Game.objects.exclude(status=Game.STATUS_BROKEN), pk=game_id)

    if request.method == 'POST':
        form = ProblemReportCreateForm(request.POST, game=game, user=request.user)
        if form.is_valid():
            ip_address = _get_request_ip(request)
            if _report_submission_rate_limit_exceeded(ip_address):
                form.add_error(None, 'Too many problem reports from this device. Please wait a few minutes and try again.')
            else:
                report = form.save(commit=False)

                # Capture device info
                user_agent = request.META.get('HTTP_USER_AGENT', '')
                report.device_info = f"{user_agent[:200]}"  # Limit to 200 chars
                report.ip_address = ip_address

                # Associate authenticated user if logged in
                if request.user.is_authenticated:
                    report.reported_by_user = request.user
                    report.reported_by_name = request.user.get_full_name() or request.user.username
                    if hasattr(request.user, 'maintainer'):
                        report.reported_by_contact = request.user.email

                report.save()

                messages.success(request, 'Problem report submitted successfully. Thank you!')
                return redirect('report_detail', pk=report.pk)
    else:
        form = ProblemReportCreateForm(game=game, user=request.user)

    return render(request, 'tickets/report_create.html', {
        'form': form,
        'game': game,
    })


@login_required
def game_list(request):
    """
    Display list of all games/machines.
    Only accessible to authenticated staff and maintainers.
    """
    # Check permission (staff users or maintainers)
    if not (request.user.is_staff or hasattr(request.user, 'maintainer')):
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('report_list')

    games = Game.objects.all().order_by('name')

    form = GameFilterForm(request.GET or None)

    if form.is_valid():
        # Search functionality
        search = form.cleaned_data.get('search')
        if search:
            games = games.filter(
                Q(name__icontains=search) |
                Q(manufacturer__icontains=search)
            )

        # Filter by type
        game_type = form.cleaned_data.get('type')
        if game_type:
            games = games.filter(type=game_type)

        # Filter by status
        status = form.cleaned_data.get('status')
        if status:
            games = games.filter(status=status)

    # Pagination
    paginator = Paginator(games, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'tickets/game_list.html', {
        'page_obj': page_obj,
        'form': form,
    })


@login_required
def game_detail(request, pk):
    """
    Display game details with recent reports.
    Only accessible to authenticated staff and maintainers.
    """
    # Check permission (staff users or maintainers)
    if not (request.user.is_staff or hasattr(request.user, 'maintainer')):
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('report_list')

    game = get_object_or_404(Game, pk=pk)

    # Get recent reports for this game
    recent_reports = ProblemReport.objects.filter(game=game).order_by('-created_at')[:10]

    return render(request, 'tickets/game_detail.html', {
        'game': game,
        'recent_reports': recent_reports,
    })


@login_required
def game_qr(request, pk):
    """
    Display QR code for a game (print-optimized page).
    Only accessible to authenticated staff and maintainers.
    """
    # Check permission (staff users or maintainers)
    if not (request.user.is_staff or hasattr(request.user, 'maintainer')):
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('report_list')

    game = get_object_or_404(Game, pk=pk)

    # Generate QR code
    # The QR code will link to the report creation page for this game
    qr_url = request.build_absolute_uri(
        reverse('report_create_qr', args=[game.pk])
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

    return render(request, 'tickets/game_qr.html', {
        'game': game,
        'qr_code_data': img_str,
        'qr_url': qr_url,
    })
