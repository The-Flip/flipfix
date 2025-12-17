from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, re_path

from the_flip.apps.accounts.forms import SimplePasswordChangeForm
from the_flip.apps.accounts.views import (
    ProfileUpdateView,
    TerminalCreateView,
    TerminalDeactivateView,
    TerminalListView,
    TerminalLoginView,
    TerminalReactivateView,
    TerminalUpdateView,
    check_username,
    invitation_register,
    self_register,
)
from the_flip.apps.catalog.views import (
    MachineActivityPartialView,
    MachineDetailViewForMaintainers,
    MachineDetailViewForPublic,
    MachineListView,
    MachineListViewForPublic,
    MachineModelUpdateView,
    MachineQuickCreateView,
    MachineUpdateView,
)
from the_flip.apps.catalog.views_inline import MachineInlineUpdateView
from the_flip.apps.core.admin_views import admin_debug_view
from the_flip.apps.core.views import HomeView, TranscodeStatusView, healthz
from the_flip.apps.maintenance import views as maintenance_views
from the_flip.apps.parts import views as parts_views
from the_flip.views import serve_media

urlpatterns = [
    #
    # Home and health check
    #
    path("", HomeView.as_view(), name="home"),  # Landing page
    path("healthz", healthz, name="healthz"),  # Health check for Railway
    #
    # Django admin
    #
    path("admin/tools/debug/", admin_debug_view, name="admin-debug-dashboard"),  # Debug dashboard
    path("admin/", admin.site.urls),  # Django admin app
    #
    # Authentication
    #
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),  # Login page
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),  # Logout
    path("register/", self_register, name="self-register"),  # Self-registration form
    path("register/check-username/", check_username, name="check-username"),  # AJAX username check
    path(
        "register/<str:token>/",
        invitation_register,
        name="invitation-register",
    ),  # Invitation-based registration
    #
    # Profile
    #
    path("profile/", ProfileUpdateView.as_view(), name="profile"),  # Edit profile
    path(
        "profile/password/",
        auth_views.PasswordChangeView.as_view(
            template_name="registration/password_change_form.html",
            form_class=SimplePasswordChangeForm,
        ),
        name="password_change",
    ),  # Change password form
    path(
        "profile/password/done/",
        auth_views.PasswordChangeDoneView.as_view(
            template_name="registration/password_change_done.html"
        ),
        name="password_change_done",
    ),  # Password change confirmation
    #
    # Shared terminal accounts
    #
    path("terminals/", TerminalListView.as_view(), name="terminal-list"),  # List terminals
    path("terminals/add/", TerminalCreateView.as_view(), name="terminal-add"),  # Create terminal
    path(
        "terminals/<int:pk>/login/", TerminalLoginView.as_view(), name="terminal-login"
    ),  # Login as terminal
    path(
        "terminals/<int:pk>/edit/", TerminalUpdateView.as_view(), name="terminal-edit"
    ),  # Edit terminal
    path(
        "terminals/<int:pk>/deactivate/",
        TerminalDeactivateView.as_view(),
        name="terminal-deactivate",
    ),  # Deactivate terminal
    path(
        "terminals/<int:pk>/reactivate/",
        TerminalReactivateView.as_view(),
        name="terminal-reactivate",
    ),  # Reactivate terminal
    #
    # Public pages (no login required)
    #
    path(
        "m/", MachineListViewForPublic.as_view(), name="public-machine-list"
    ),  # Public machine list
    path(
        "m/<slug:slug>/", MachineDetailViewForPublic.as_view(), name="public-machine-detail"
    ),  # Public machine detail
    path(
        "p/<slug:slug>/",
        maintenance_views.PublicProblemReportCreateView.as_view(),
        name="public-problem-report-create",
    ),  # Public problem report form (from QR code)
    #
    # Problem reports (maintainer)
    #
    path(
        "problem-reports/",
        maintenance_views.ProblemReportListView.as_view(),
        name="problem-report-list",
    ),  # List all problem reports
    path(
        "problem-reports/entries/",
        maintenance_views.ProblemReportListPartialView.as_view(),
        name="problem-report-list-entries",
    ),  # AJAX: infinite scroll for problem report list
    path(
        "problem-reports/new/",
        maintenance_views.ProblemReportCreateView.as_view(),
        name="problem-report-create",
    ),  # Create problem report (no machine pre-selected)
    path(
        "machines/<slug:slug>/problem-reports/new/",
        maintenance_views.ProblemReportCreateView.as_view(),
        name="problem-report-create-machine",
    ),  # Create problem report for specific machine
    path(
        "problem-reports/<int:pk>/",
        maintenance_views.ProblemReportDetailView.as_view(),
        name="problem-report-detail",
    ),  # Problem report detail page
    path(
        "problem-reports/<int:pk>/log-entries/",
        maintenance_views.ProblemReportLogEntriesPartialView.as_view(),
        name="problem-report-log-entries",
    ),  # AJAX: infinite scroll for log entries on problem report
    path(
        "problem-reports/<slug:slug>/",
        maintenance_views.MachineProblemReportListView.as_view(),
        name="machine-problem-reports",
    ),  # List problem reports for a machine
    #
    # Machines (maintainer)
    #
    path(
        "machines/", MachineListView.as_view(), name="maintainer-machine-list"
    ),  # List all machines
    path(
        "machines/new/", MachineQuickCreateView.as_view(), name="machine-quick-create"
    ),  # Quick create machine
    path(
        "machines/<slug:slug>/",
        MachineDetailViewForMaintainers.as_view(),
        name="maintainer-machine-detail",
    ),  # Machine detail/feed page
    path(
        "machines/<slug:slug>/activity/",
        MachineActivityPartialView.as_view(),
        name="machine-activity-entries",
    ),  # AJAX: infinite scroll for machine activity feed
    path(
        "machines/<slug:slug>/edit/", MachineUpdateView.as_view(), name="machine-edit"
    ),  # Edit machine
    path(
        "machines/<slug:slug>/qr/", maintenance_views.MachineQRView.as_view(), name="machine-qr"
    ),  # QR code page
    path(
        "qr_codes/", maintenance_views.MachineBulkQRCodeView.as_view(), name="machine-qr-bulk"
    ),  # Bulk QR codes
    path(
        "machines/<slug:slug>/update/",
        MachineInlineUpdateView.as_view(),
        name="machine-inline-update",
    ),  # AJAX: update machine status/location from dropdown
    #
    # Machine models
    #
    path(
        "models/<slug:slug>/edit/", MachineModelUpdateView.as_view(), name="machine-model-edit"
    ),  # Edit machine model
    #
    # API endpoints
    #
    path(
        "api/transcoding/download/<str:model_name>/<int:media_id>/",
        maintenance_views.ServeSourceMediaView.as_view(),
        name="api-transcoding-download",
    ),  # Worker: download source video for transcoding
    path(
        "api/transcoding/upload/<str:model_name>/<int:media_id>/",
        maintenance_views.ReceiveTranscodedMediaView.as_view(),
        name="api-transcoding-upload",
    ),  # Worker: upload transcoded video and poster
    path(
        "api/transcode/status/",
        TranscodeStatusView.as_view(),
        name="api-transcode-status",
    ),  # AJAX: poll video transcode status
    path(
        "api/maintainers/",
        maintenance_views.MaintainerAutocompleteView.as_view(),
        name="api-maintainer-autocomplete",
    ),  # AJAX: maintainer autocomplete for forms
    path(
        "api/machines/",
        maintenance_views.MachineAutocompleteView.as_view(),
        name="api-machine-autocomplete",
    ),  # AJAX: machine autocomplete for forms
    path(
        "api/problem-reports/",
        maintenance_views.ProblemReportAutocompleteView.as_view(),
        name="api-problem-report-autocomplete",
    ),  # AJAX: problem report autocomplete for log entry reassignment
    #
    # Log entries
    #
    path("logs/", maintenance_views.LogListView.as_view(), name="log-list"),  # List all log entries
    path(
        "logs/entries/", maintenance_views.LogListPartialView.as_view(), name="log-list-entries"
    ),  # AJAX: infinite scroll for log list
    path(
        "logs/new/", maintenance_views.MachineLogCreateView.as_view(), name="log-create-global"
    ),  # Create log entry (no machine pre-selected)
    path(
        "logs/<int:pk>/", maintenance_views.LogEntryDetailView.as_view(), name="log-detail"
    ),  # Log entry detail page
    path(
        "logs/new/<slug:slug>/",
        maintenance_views.MachineLogCreateView.as_view(),
        name="log-create-machine",
    ),  # Create log entry for specific machine
    path(
        "logs/new/problem-report/<int:pk>/",
        maintenance_views.MachineLogCreateView.as_view(),
        name="log-create-problem-report",
    ),  # Create log entry linked to problem report
    path(
        "logs/<slug:slug>/entries/",
        maintenance_views.MachineLogPartialView.as_view(),
        name="log-entries",
    ),  # AJAX: infinite scroll for machine log page
    path(
        "logs/<slug:slug>/", maintenance_views.MachineLogView.as_view(), name="log-machine"
    ),  # Machine log page
    #
    # Parts requests
    #
    path(
        "parts/", parts_views.PartRequestListView.as_view(), name="part-request-list"
    ),  # List all part requests
    path(
        "parts/entries/",
        parts_views.PartRequestListPartialView.as_view(),
        name="part-request-list-entries",
    ),  # AJAX: infinite scroll for part request list
    path(
        "parts/new/", parts_views.PartRequestCreateView.as_view(), name="part-request-create"
    ),  # Create part request (no machine pre-selected)
    path(
        "parts/new/<slug:slug>/",
        parts_views.PartRequestCreateView.as_view(),
        name="part-request-create-machine",
    ),  # Create part request for specific machine
    path(
        "parts/<int:pk>/",
        parts_views.PartRequestDetailView.as_view(),
        name="part-request-detail",
    ),  # Part request detail page
    path(
        "parts/<int:pk>/update/",
        parts_views.PartRequestUpdateCreateView.as_view(),
        name="part-request-update-create",
    ),  # Create update/comment on part request (form page)
    path(
        "parts/<int:pk>/status/",
        parts_views.PartRequestStatusUpdateView.as_view(),
        name="part-request-status-update",
    ),  # AJAX: update part request status from dropdown
    path(
        "parts/<int:pk>/updates/",
        parts_views.PartRequestUpdatesPartialView.as_view(),
        name="part-request-updates",
    ),  # AJAX: infinite scroll for updates on part request detail
    path(
        "parts/updates/<int:pk>/",
        parts_views.PartRequestUpdateDetailView.as_view(),
        name="part-request-update-detail",
    ),  # Part request update detail page
]

media_url = settings.MEDIA_URL.lstrip("/")
if media_url:
    urlpatterns += [
        re_path(rf"^{media_url}(?P<path>.*)$", serve_media, name="media"),  # Serve media files
    ]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
