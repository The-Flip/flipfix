from django.conf import settings
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
    invitation_register,
)
from the_flip.apps.catalog.views import (
    MachineCreateLandingView,
    MachineCreateModelDoesNotExistView,
    MachineCreateModelExistsView,
    MachineDetailViewForPublic,
    MachineFeedPartialView,
    MachineFeedView,
    MachineListView,
    MachineListViewForPublic,
    MachineModelUpdateView,
    MachineUpdateView,
)
from the_flip.apps.catalog.views_inline import MachineInlineUpdateView
from the_flip.apps.core.admin_views import admin_debug_view
from the_flip.apps.core.views.feed import GlobalActivityFeedPartialView
from the_flip.apps.core.views.health import healthz
from the_flip.apps.core.views.home import HomeView
from the_flip.apps.core.views.link_targets import LinkTargetsView, LinkTypesView
from the_flip.apps.core.views.transcode import TranscodeStatusView
from the_flip.apps.maintenance.views.autocomplete import (
    MachineAutocompleteView,
    MaintainerAutocompleteView,
    ProblemReportAutocompleteView,
)
from the_flip.apps.maintenance.views.log_entries import (
    LogEntryDetailView,
    LogEntryEditView,
    LogListPartialView,
    LogListView,
    MachineLogCreateView,
)
from the_flip.apps.maintenance.views.media_api import ReceiveMediaView
from the_flip.apps.maintenance.views.problem_reports import (
    ProblemReportCreateView,
    ProblemReportDetailView,
    ProblemReportEditView,
    ProblemReportListView,
    ProblemReportLogEntriesPartialView,
    PublicProblemReportCreateView,
)
from the_flip.apps.maintenance.views.qr_codes import MachineBulkQRCodeView, MachineQRView
from the_flip.apps.maintenance.views.transcoding import (
    ReceiveTranscodedMediaView,
    ServeSourceMediaView,
)
from the_flip.apps.maintenance.views.wall_display import (
    WallDisplayBoardView,
    WallDisplaySetupView,
)
from the_flip.apps.parts.views.part_request_updates import (
    PartRequestUpdateCreateView,
    PartRequestUpdateDetailView,
    PartRequestUpdateEditView,
)
from the_flip.apps.parts.views.part_requests import (
    PartRequestCreateView,
    PartRequestDetailView,
    PartRequestEditView,
    PartRequestListPartialView,
    PartRequestListView,
    PartRequestStatusUpdateView,
    PartRequestUpdatesPartialView,
)
from the_flip.apps.wiki.views import (
    WikiHomeView,
    WikiPageCreateView,
    WikiPageDeleteView,
    WikiPageDetailView,
    WikiPageEditView,
    WikiReorderSaveView,
    WikiReorderView,
    WikiSearchView,
    WikiTagAutocompleteView,
    WikiTemplateContentView,
    WikiTemplateListView,
    WikiTemplatePrefillView,
)
from the_flip.views import serve_media

urlpatterns = [
    #
    # Home and health check
    #
    path("", HomeView.as_view(), name="home"),  # Landing page
    path(
        "activity/entries/",
        GlobalActivityFeedPartialView.as_view(),
        name="global-activity-feed-entries",
    ),  # AJAX: infinite scroll for global activity feed
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
        PublicProblemReportCreateView.as_view(),
        name="public-problem-report-create",
    ),  # Public problem report form (from QR code)
    #
    # Problem reports (maintainer)
    #
    path(
        "problem-reports/",
        ProblemReportListView.as_view(),
        name="problem-report-list",
    ),  # List all problem reports
    path(
        "problem-reports/new/",
        ProblemReportCreateView.as_view(),
        name="problem-report-create",
    ),  # Create problem report (no machine pre-selected)
    path(
        "machines/<slug:slug>/problem-reports/new/",
        ProblemReportCreateView.as_view(),
        name="problem-report-create-machine",
    ),  # Create problem report for specific machine
    path(
        "problem-reports/<int:pk>/",
        ProblemReportDetailView.as_view(),
        name="problem-report-detail",
    ),  # Problem report detail page
    path(
        "problem-reports/<int:pk>/edit/",
        ProblemReportEditView.as_view(),
        name="problem-report-edit",
    ),  # Edit problem report metadata
    path(
        "problem-reports/<int:pk>/log-entries/",
        ProblemReportLogEntriesPartialView.as_view(),
        name="problem-report-log-entries",
    ),  # AJAX: infinite scroll for log entries on problem report
    #
    # Wall display
    #
    path("wall/", WallDisplaySetupView.as_view(), name="wall-display-setup"),  # Wall display setup
    path(
        "wall/board/", WallDisplayBoardView.as_view(), name="wall-display-board"
    ),  # Wall display board
    #
    # Machines (maintainer)
    #
    path(
        "machines/", MachineListView.as_view(), name="maintainer-machine-list"
    ),  # List all machines
    path(
        "machines/new/", MachineCreateLandingView.as_view(), name="machine-create-landing"
    ),  # Landing page: select model
    path(
        "machines/new/model-does-not-exist/",
        MachineCreateModelDoesNotExistView.as_view(),
        name="machine-create-model-does-not-exist",
    ),  # Create new model + instance
    path(
        "machines/new/<slug:model_slug>/",
        MachineCreateModelExistsView.as_view(),
        name="machine-create-model-exists",
    ),  # Add instance of existing model
    path(
        "machines/<slug:slug>/",
        MachineFeedView.as_view(),
        name="maintainer-machine-detail",
    ),  # Machine detail/feed page
    path(
        "machines/<slug:slug>/entries/",
        MachineFeedPartialView.as_view(),
        name="machine-feed-entries",
    ),  # AJAX: infinite scroll for machine feed (supports ?f= filter)
    path(
        "machines/<slug:slug>/edit/", MachineUpdateView.as_view(), name="machine-edit"
    ),  # Edit machine
    path("machines/<slug:slug>/qr/", MachineQRView.as_view(), name="machine-qr"),  # QR code page
    path("qr_codes/", MachineBulkQRCodeView.as_view(), name="machine-qr-bulk"),  # Bulk QR codes
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
        ServeSourceMediaView.as_view(),
        name="api-transcoding-download",
    ),  # Worker: download source video for transcoding
    path(
        "api/transcoding/upload/<str:model_name>/<int:media_id>/",
        ReceiveTranscodedMediaView.as_view(),
        name="api-transcoding-upload",
    ),  # Worker: upload transcoded video and poster
    path(
        "api/media/<str:model_name>/<int:parent_id>/",
        ReceiveMediaView.as_view(),
        name="api-media-upload",
    ),  # Discord bot: upload media file
    path(
        "api/transcoding/status/",
        TranscodeStatusView.as_view(),
        name="api-transcoding-status",
    ),  # AJAX: poll video transcode status
    path(
        "api/maintainers/",
        MaintainerAutocompleteView.as_view(),
        name="api-maintainer-autocomplete",
    ),  # AJAX: maintainer autocomplete for forms
    path(
        "api/machines/",
        MachineAutocompleteView.as_view(),
        name="api-machine-autocomplete",
    ),  # AJAX: machine autocomplete for forms
    path(
        "api/problem-reports/",
        ProblemReportAutocompleteView.as_view(),
        name="api-problem-report-autocomplete",
    ),  # AJAX: problem report autocomplete for log entry reassignment
    #
    # Log entries
    #
    path("logs/", LogListView.as_view(), name="log-list"),  # List all log entries
    path(
        "logs/entries/", LogListPartialView.as_view(), name="log-list-entries"
    ),  # AJAX: infinite scroll for log list
    path(
        "logs/new/", MachineLogCreateView.as_view(), name="log-create-global"
    ),  # Create log entry (no machine pre-selected)
    path(
        "logs/<int:pk>/", LogEntryDetailView.as_view(), name="log-detail"
    ),  # Log entry detail page
    path(
        "logs/<int:pk>/edit/", LogEntryEditView.as_view(), name="log-entry-edit"
    ),  # Edit log entry metadata
    path(
        "logs/new/<slug:slug>/",
        MachineLogCreateView.as_view(),
        name="log-create-machine",
    ),  # Create log entry for specific machine
    path(
        "logs/new/problem-report/<int:pk>/",
        MachineLogCreateView.as_view(),
        name="log-create-problem-report",
    ),  # Create log entry linked to problem report
    #
    # Parts requests
    #
    path(
        "parts/", PartRequestListView.as_view(), name="part-request-list"
    ),  # List all part requests
    path(
        "parts/entries/",
        PartRequestListPartialView.as_view(),
        name="part-request-list-entries",
    ),  # AJAX: infinite scroll for part request list
    path(
        "parts/new/", PartRequestCreateView.as_view(), name="part-request-create"
    ),  # Create part request (no machine pre-selected)
    path(
        "parts/new/<slug:slug>/",
        PartRequestCreateView.as_view(),
        name="part-request-create-machine",
    ),  # Create part request for specific machine
    path(
        "parts/<int:pk>/",
        PartRequestDetailView.as_view(),
        name="part-request-detail",
    ),  # Part request detail page
    path(
        "parts/<int:pk>/edit/",
        PartRequestEditView.as_view(),
        name="part-request-edit",
    ),  # Edit part request metadata
    path(
        "parts/<int:pk>/update/",
        PartRequestUpdateCreateView.as_view(),
        name="part-request-update-create",
    ),  # Create update/comment on part request (form page)
    path(
        "parts/<int:pk>/status/",
        PartRequestStatusUpdateView.as_view(),
        name="part-request-status-update",
    ),  # AJAX: update part request status from dropdown
    path(
        "parts/<int:pk>/updates/",
        PartRequestUpdatesPartialView.as_view(),
        name="part-request-updates",
    ),  # AJAX: infinite scroll for updates on part request detail
    path(
        "parts/updates/<int:pk>/",
        PartRequestUpdateDetailView.as_view(),
        name="part-request-update-detail",
    ),  # Part request update detail page
    path(
        "parts/updates/<int:pk>/edit/",
        PartRequestUpdateEditView.as_view(),
        name="part-request-update-edit",
    ),  # Edit part request update metadata
    #
    # Cross-record link autocomplete API
    #
    path(
        "api/link-types/",
        LinkTypesView.as_view(),
        name="api-link-types",
    ),  # AJAX: available link types for [[ type picker
    path(
        "api/link-targets/",
        LinkTargetsView.as_view(),
        name="api-link-targets",
    ),  # AJAX: link target autocomplete for [[ syntax
    #
    # Wiki
    #
    path("wiki/", WikiHomeView.as_view(), name="wiki-home"),  # Wiki home/index
    path("wiki/search/", WikiSearchView.as_view(), name="wiki-search"),  # Wiki search
    path("wiki/create/", WikiPageCreateView.as_view(), name="wiki-page-create"),  # Create page
    path("wiki/reorder/", WikiReorderView.as_view(), name="wiki-reorder"),  # Reorder nav
    path(
        "wiki/templates/<int:page_pk>/<str:template_name>/",
        WikiTemplatePrefillView.as_view(),
        name="wiki-template-prefill",
    ),  # Template block → pre-fill create form
    path(
        "wiki/doc/<path:path>", WikiPageDetailView.as_view(), name="wiki-page-detail"
    ),  # Wiki page detail (path = tag/slug or just slug)
    path("wiki/edit/<path:path>", WikiPageEditView.as_view(), name="wiki-page-edit"),  # Edit page
    path(
        "wiki/delete/<path:path>", WikiPageDeleteView.as_view(), name="wiki-page-delete"
    ),  # Delete page
    path(
        "api/wiki/tags/", WikiTagAutocompleteView.as_view(), name="api-wiki-tag-autocomplete"
    ),  # AJAX: wiki tag autocomplete
    path(
        "api/wiki/reorder/", WikiReorderSaveView.as_view(), name="api-wiki-reorder"
    ),  # AJAX: save wiki nav reorder
    path(
        "api/wiki/templates/",
        WikiTemplateListView.as_view(),
        name="api-wiki-template-list",
    ),  # AJAX: list matching template options for create forms
    path(
        "api/wiki/templates/<int:page_pk>/<str:template_name>/content/",
        WikiTemplateContentView.as_view(),
        name="api-wiki-template-content",
    ),  # AJAX: fetch template block content
]

# Serve user-uploaded media files
media_url_prefix = settings.MEDIA_URL.lstrip("/")
if media_url_prefix:
    urlpatterns += [
        re_path(rf"^{media_url_prefix}(?P<path>.*)$", serve_media, name="media"),
    ]
