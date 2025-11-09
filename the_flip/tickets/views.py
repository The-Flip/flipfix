from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.views import LoginView
from django.core.paginator import Paginator
from django.db.models import Q

from .models import Game, ProblemReport
from .forms import ReportFilterForm, ReportUpdateForm, ProblemReportCreateForm


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

    # Apply filters
    form = ReportFilterForm(request.GET or None)
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

    # Check if user can update
    can_update = request.user.is_authenticated and hasattr(request.user, 'maintainer')

    form = None

    # Handle POST requests (maintainers only)
    if request.method == 'POST' and can_update:
        if 'add_update' in request.POST:
            form = ReportUpdateForm(request.POST)
            if form.is_valid():
                text = form.cleaned_data['text']
                report.add_note(request.user.maintainer, text)
                messages.success(request, 'Update added successfully.')
                return redirect('report_detail', pk=pk)

        elif 'close_report' in request.POST:
            text = request.POST.get('text', 'Closing report.')
            if not text or text.strip() == '':
                text = 'Closing report.'
            report.set_status(ProblemReport.STATUS_CLOSED, request.user.maintainer, text)
            messages.success(request, 'Report closed successfully.')
            return redirect('report_detail', pk=pk)

        elif 'reopen_report' in request.POST:
            text = request.POST.get('text', 'Reopening report.')
            if not text or text.strip() == '':
                text = 'Reopening report.'
            report.set_status(ProblemReport.STATUS_OPEN, request.user.maintainer, text)
            messages.success(request, 'Report reopened successfully.')
            return redirect('report_detail', pk=pk)

    # Create empty form for GET requests or failed POST
    if can_update and form is None:
        form = ReportUpdateForm()

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
        game = get_object_or_404(Game, pk=game_id, is_active=True)

    if request.method == 'POST':
        form = ProblemReportCreateForm(request.POST, game=game)
        if form.is_valid():
            report = form.save(commit=False)

            # Capture device info
            user_agent = request.META.get('HTTP_USER_AGENT', '')
            ip_address = request.META.get('REMOTE_ADDR', '')
            report.device_info = f"{user_agent[:200]}"  # Limit to 200 chars

            # Associate authenticated user if logged in
            if request.user.is_authenticated and hasattr(request.user, 'maintainer'):
                if not report.reported_by_name:
                    report.reported_by_name = request.user.get_full_name() or request.user.username

            report.save()

            messages.success(request, 'Problem report submitted successfully. Thank you!')
            return redirect('report_detail', pk=report.pk)
    else:
        form = ProblemReportCreateForm(game=game)

    return render(request, 'tickets/report_create.html', {
        'form': form,
        'game': game,
    })
