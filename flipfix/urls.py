from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import re_path
from django.views.generic import RedirectView

from flipfix.apps.accounts.forms import SimplePasswordChangeForm
from flipfix.apps.accounts.views import (
    ProfileUpdateView,
    TerminalCreateView,
    TerminalDeactivateView,
    TerminalListView,
    TerminalLoginView,
    TerminalReactivateView,
    TerminalUpdateView,
    invitation_register,
)
from flipfix.apps.catalog.views import (
    MachineCreateLandingView,
    MachineCreateModelDoesNotExistView,
    MachineCreateModelExistsView,
    MachineDetailViewForPublic,
    MachineFeedPartialView,
    MachineFeedView,
    MachineListView,
    MachineModelUpdateView,
    MachineUpdateView,
)
from flipfix.apps.catalog.views_inline import MachineInlineUpdateView
from flipfix.apps.core.admin_views import admin_debug_view
from flipfix.apps.core.routing import path
from flipfix.apps.core.views.feed import GlobalActivityFeedPartialView
from flipfix.apps.core.views.health import healthz
from flipfix.apps.core.views.home import HomeView, SiteSettingsEditView
from flipfix.apps.core.views.link_targets import LinkTargetsView, LinkTypesView
from flipfix.apps.core.views.transcode import TranscodeStatusView
from flipfix.apps.maintenance.views.autocomplete import (
    MachineAutocompleteView,
    MaintainerAutocompleteView,
    ProblemReportAutocompleteView,
)
from flipfix.apps.maintenance.views.log_entries import (
    LogEntryDetailView,
    LogEntryEditView,
    LogListPartialView,
    LogListView,
    MachineLogCreateView,
)
from flipfix.apps.maintenance.views.media_api import ReceiveMediaView
from flipfix.apps.maintenance.views.problem_reports import (
    ProblemReportCreateView,
    ProblemReportDetailView,
    ProblemReportEditView,
    ProblemReportListView,
    ProblemReportLogEntriesPartialView,
    PublicProblemReportCreateView,
)
from flipfix.apps.maintenance.views.qr_codes import MachineBulkQRCodeView, MachineQRView
from flipfix.apps.maintenance.views.transcoding import (
    ReceiveTranscodedMediaView,
    ServeSourceMediaView,
)
from flipfix.apps.maintenance.views.wall_display import (
    WallDisplayBoardView,
    WallDisplaySetupView,
)
from flipfix.apps.parts.views.part_request_updates import (
    PartRequestUpdateCreateView,
    PartRequestUpdateDetailView,
    PartRequestUpdateEditView,
)
from flipfix.apps.parts.views.part_requests import (
    PartRequestCreateView,
    PartRequestDetailView,
    PartRequestEditView,
    PartRequestListPartialView,
    PartRequestListView,
    PartRequestStatusUpdateView,
    PartRequestUpdatesPartialView,
)
from flipfix.apps.wiki.views import (
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
from flipfix.views import serve_media

urlpatterns = [
    ###
    # Home and health check
    ###
    # Landing page
    path("", HomeView.as_view(), name="home", access="always_public"),
    # AJAX: infinite scroll for global activity feed
    path(
        "activity/entries/",
        GlobalActivityFeedPartialView.as_view(),
        name="global-activity-feed-entries",
    ),
    # Health check for Railway
    path("healthz", healthz, name="healthz", access="always_public"),
    ###
    # Django admin
    ###
    # Debug dashboard
    path("admin/tools/debug/", admin_debug_view, name="admin-debug-dashboard"),
    # Django admin app
    path("admin/", admin.site.urls),
    ###
    # Authentication
    ###
    # Login page
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
        access="always_public",
    ),
    # Logout
    path("logout/", auth_views.LogoutView.as_view(), name="logout", access="always_public"),
    # Invitation-based registration
    path(
        "register/<str:token>/",
        invitation_register,
        name="invitation-register",
        access="always_public",
    ),
    ###
    # Profile
    ###
    # Edit profile
    path("profile/", ProfileUpdateView.as_view(), name="profile", access="authenticated"),
    # Change password form
    path(
        "profile/password/",
        auth_views.PasswordChangeView.as_view(
            template_name="registration/password_change_form.html",
            form_class=SimplePasswordChangeForm,
        ),
        name="password_change",
        access="authenticated",
    ),
    # Password change confirmation
    path(
        "profile/password/done/",
        auth_views.PasswordChangeDoneView.as_view(
            template_name="registration/password_change_done.html"
        ),
        name="password_change_done",
        access="authenticated",
    ),
    ###
    # Shared terminal accounts
    ###
    path("terminals/", TerminalListView.as_view(), name="terminal-list", access="superuser"),
    path("terminals/add/", TerminalCreateView.as_view(), name="terminal-add", access="superuser"),
    path(
        "terminals/<int:pk>/login/",
        TerminalLoginView.as_view(),
        name="terminal-login",
        access="superuser",
    ),
    path(
        "terminals/<int:pk>/edit/",
        TerminalUpdateView.as_view(),
        name="terminal-edit",
        access="superuser",
    ),
    path(
        "terminals/<int:pk>/deactivate/",
        TerminalDeactivateView.as_view(),
        name="terminal-deactivate",
        access="superuser",
    ),
    path(
        "terminals/<int:pk>/reactivate/",
        TerminalReactivateView.as_view(),
        name="terminal-reactivate",
        access="superuser",
    ),
    ###
    # Site settings (superuser)
    ###
    path(
        "settings/site/", SiteSettingsEditView.as_view(), name="site-settings", access="superuser"
    ),
    ###
    # Public pages (no login required)
    ###
    # Public machine detail
    path(
        "m/<slug:slug>/",
        MachineDetailViewForPublic.as_view(),
        name="public-machine-detail",
        access="always_public",
    ),
    # Public problem report form (from QR code)
    path(
        "p/<slug:slug>/",
        PublicProblemReportCreateView.as_view(),
        name="public-problem-report-create",
        access="always_public",
    ),
    ###
    # Problem reports
    ###
    # List all problem reports
    path(
        "problem-reports/",
        ProblemReportListView.as_view(),
        name="problem-report-list",
        access="public",
    ),
    # Create problem report (no machine pre-selected)
    path(
        "problem-reports/new/",
        ProblemReportCreateView.as_view(),
        name="problem-report-create",
    ),
    # Create problem report for specific machine
    path(
        "machines/<slug:slug>/problem-reports/new/",
        ProblemReportCreateView.as_view(),
        name="problem-report-create-machine",
    ),
    # Problem report detail page
    path(
        "problem-reports/<int:pk>/",
        ProblemReportDetailView.as_view(),
        name="problem-report-detail",
        access="public",
    ),
    # Edit problem report metadata
    path(
        "problem-reports/<int:pk>/edit/",
        ProblemReportEditView.as_view(),
        name="problem-report-edit",
    ),
    # AJAX: infinite scroll for log entries on problem report
    path(
        "problem-reports/<int:pk>/log-entries/",
        ProblemReportLogEntriesPartialView.as_view(),
        name="problem-report-log-entries",
        access="public",
    ),
    ###
    # Wall display
    ###
    # Wall display setup
    path("wall/", WallDisplaySetupView.as_view(), name="wall-display-setup"),
    # Wall display board
    path("wall/board/", WallDisplayBoardView.as_view(), name="wall-display-board"),
    ###
    # Machines
    ###
    # List all machines
    path("machines/", MachineListView.as_view(), name="maintainer-machine-list", access="public"),
    # Landing page: select model
    path("machines/new/", MachineCreateLandingView.as_view(), name="machine-create-landing"),
    # Create new model + instance
    path(
        "machines/new/model-does-not-exist/",
        MachineCreateModelDoesNotExistView.as_view(),
        name="machine-create-model-does-not-exist",
    ),
    # Add instance of existing model
    path(
        "machines/new/<slug:model_slug>/",
        MachineCreateModelExistsView.as_view(),
        name="machine-create-model-exists",
    ),
    # Machine detail/feed page
    path(
        "machines/<slug:slug>/",
        MachineFeedView.as_view(),
        name="maintainer-machine-detail",
        access="public",
    ),
    # AJAX: infinite scroll for machine feed (supports ?f= filter)
    path(
        "machines/<slug:slug>/entries/",
        MachineFeedPartialView.as_view(),
        name="machine-feed-entries",
        access="public",
    ),
    # Edit machine
    path("machines/<slug:slug>/edit/", MachineUpdateView.as_view(), name="machine-edit"),
    # QR code page
    path("machines/<slug:slug>/qr/", MachineQRView.as_view(), name="machine-qr"),
    # Bulk QR codes
    path("qr_codes/", MachineBulkQRCodeView.as_view(), name="machine-qr-bulk"),
    # AJAX: update machine status/location from dropdown
    path(
        "machines/<slug:slug>/update/",
        MachineInlineUpdateView.as_view(),
        name="machine-inline-update",
    ),
    ###
    # Machine models
    ###
    # Edit machine model
    path("models/<slug:slug>/edit/", MachineModelUpdateView.as_view(), name="machine-model-edit"),
    ###
    # API endpoints
    ###
    # Worker: download source video for transcoding
    path(
        "api/transcoding/download/<str:model_name>/<int:media_id>/",
        ServeSourceMediaView.as_view(),
        name="api-transcoding-download",
        access="always_public",
    ),
    # Worker: upload transcoded video and poster
    path(
        "api/transcoding/upload/<str:model_name>/<int:media_id>/",
        ReceiveTranscodedMediaView.as_view(),
        name="api-transcoding-upload",
        access="always_public",
    ),
    # Discord bot: upload media file
    path(
        "api/media/<str:model_name>/<int:parent_id>/",
        ReceiveMediaView.as_view(),
        name="api-media-upload",
        access="always_public",
    ),
    # AJAX: poll video transcode status
    path(
        "api/transcoding/status/",
        TranscodeStatusView.as_view(),
        name="api-transcoding-status",
    ),
    # AJAX: maintainer autocomplete for forms
    path(
        "api/maintainers/",
        MaintainerAutocompleteView.as_view(),
        name="api-maintainer-autocomplete",
    ),
    # AJAX: machine autocomplete for forms
    path(
        "api/machines/",
        MachineAutocompleteView.as_view(),
        name="api-machine-autocomplete",
    ),
    # AJAX: problem report autocomplete for log entry reassignment
    path(
        "api/problem-reports/",
        ProblemReportAutocompleteView.as_view(),
        name="api-problem-report-autocomplete",
    ),
    ###
    # Log entries
    ###
    # List all log entries
    path("logs/", LogListView.as_view(), name="log-list", access="public"),
    # AJAX: infinite scroll for log list
    path("logs/entries/", LogListPartialView.as_view(), name="log-list-entries", access="public"),
    # Create log entry (no machine pre-selected)
    path("logs/new/", MachineLogCreateView.as_view(), name="log-create-global"),
    # Log entry detail page
    path("logs/<int:pk>/", LogEntryDetailView.as_view(), name="log-detail", access="public"),
    # Edit log entry metadata
    path("logs/<int:pk>/edit/", LogEntryEditView.as_view(), name="log-entry-edit"),
    # Create log entry for specific machine
    path(
        "logs/new/<slug:slug>/",
        MachineLogCreateView.as_view(),
        name="log-create-machine",
    ),
    # Create log entry linked to problem report
    path(
        "logs/new/problem-report/<int:pk>/",
        MachineLogCreateView.as_view(),
        name="log-create-problem-report",
    ),
    ###
    # Parts requests
    ###
    # List all part requests
    path("parts/", PartRequestListView.as_view(), name="part-request-list"),
    # AJAX: infinite scroll for part request list
    path(
        "parts/entries/",
        PartRequestListPartialView.as_view(),
        name="part-request-list-entries",
    ),
    # Create part request (no machine pre-selected)
    path("parts/new/", PartRequestCreateView.as_view(), name="part-request-create"),
    # Create part request for specific machine
    path(
        "parts/new/<slug:slug>/",
        PartRequestCreateView.as_view(),
        name="part-request-create-machine",
    ),
    # Part request detail page
    path(
        "parts/<int:pk>/",
        PartRequestDetailView.as_view(),
        name="part-request-detail",
    ),
    # Edit part request metadata
    path(
        "parts/<int:pk>/edit/",
        PartRequestEditView.as_view(),
        name="part-request-edit",
    ),
    # Create update/comment on part request (form page)
    path(
        "parts/<int:pk>/update/",
        PartRequestUpdateCreateView.as_view(),
        name="part-request-update-create",
    ),
    # AJAX: update part request status from dropdown
    path(
        "parts/<int:pk>/status/",
        PartRequestStatusUpdateView.as_view(),
        name="part-request-status-update",
    ),
    # AJAX: infinite scroll for updates on part request detail
    path(
        "parts/<int:pk>/updates/",
        PartRequestUpdatesPartialView.as_view(),
        name="part-request-updates",
    ),
    # Part request update detail page
    path(
        "parts/updates/<int:pk>/",
        PartRequestUpdateDetailView.as_view(),
        name="part-request-update-detail",
    ),
    # Edit part request update metadata
    path(
        "parts/updates/<int:pk>/edit/",
        PartRequestUpdateEditView.as_view(),
        name="part-request-update-edit",
    ),
    ###
    # Cross-record link autocomplete API
    ###
    # AJAX: available link types for [[ type picker
    path("api/link-types/", LinkTypesView.as_view(), name="api-link-types"),
    # AJAX: link target autocomplete for [[ syntax
    path("api/link-targets/", LinkTargetsView.as_view(), name="api-link-targets"),
    ###
    # Wiki
    ###
    # Wiki home/index
    path("wiki/", WikiHomeView.as_view(), name="wiki-home"),
    # Wiki search
    path("wiki/search/", WikiSearchView.as_view(), name="wiki-search"),
    # Create page
    path("wiki/create/", WikiPageCreateView.as_view(), name="wiki-page-create"),
    # Reorder nav
    path("wiki/reorder/", WikiReorderView.as_view(), name="wiki-reorder"),
    # Template block → pre-fill create form
    path(
        "wiki/templates/<int:page_pk>/<str:template_name>/",
        WikiTemplatePrefillView.as_view(),
        name="wiki-template-prefill",
    ),
    # Wiki page detail (shorter URL, not under /wiki/)
    path("doc/<path:path>", WikiPageDetailView.as_view(), name="wiki-page-detail"),
    # 301 redirect: old /wiki/doc/ → new /doc/
    path(
        "wiki/doc/<path:path>",
        RedirectView.as_view(pattern_name="wiki-page-detail", permanent=True),
    ),
    # Edit page
    path("wiki/edit/<path:path>", WikiPageEditView.as_view(), name="wiki-page-edit"),
    # Delete page
    path("wiki/delete/<path:path>", WikiPageDeleteView.as_view(), name="wiki-page-delete"),
    # AJAX: wiki tag autocomplete
    path("api/wiki/tags/", WikiTagAutocompleteView.as_view(), name="api-wiki-tag-autocomplete"),
    # AJAX: save wiki nav reorder
    path("api/wiki/reorder/", WikiReorderSaveView.as_view(), name="api-wiki-reorder"),
    # AJAX: list matching template options for create forms
    path(
        "api/wiki/templates/",
        WikiTemplateListView.as_view(),
        name="api-wiki-template-list",
    ),
    # AJAX: fetch template block content
    path(
        "api/wiki/templates/<int:page_pk>/<str:template_name>/content/",
        WikiTemplateContentView.as_view(),
        name="api-wiki-template-content",
    ),
]

# Serve user-uploaded media files
media_url_prefix = settings.MEDIA_URL.lstrip("/")
if media_url_prefix:
    urlpatterns += [
        re_path(rf"^{media_url_prefix}(?P<path>.*)$", serve_media, name="media"),
    ]
