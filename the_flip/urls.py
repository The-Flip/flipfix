from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, re_path

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
    MachineDetailView,
    MachineListView,
    MachineModelUpdateView,
    MachineQuickCreateView,
    MachineUpdateView,
    PublicMachineDetailView,
    PublicMachineListView,
)
from the_flip.apps.core.views import HomeView
from the_flip.apps.maintenance import views as maintenance_views
from the_flip.views import serve_media

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    # Django admin app
    path("admin/", admin.site.urls),
    # Authentication
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    # Self-registration (beta)
    path("register/", self_register, name="self-register"),
    path("register/check-username/", check_username, name="check-username"),
    # Invitation-based registration
    path(
        "register/<str:token>/",
        invitation_register,
        name="invitation-register",
    ),
    # Profile
    path("profile/", ProfileUpdateView.as_view(), name="profile"),
    path(
        "profile/password/",
        auth_views.PasswordChangeView.as_view(
            template_name="registration/password_change_form.html"
        ),
        name="password_change",
    ),
    path(
        "profile/password/done/",
        auth_views.PasswordChangeDoneView.as_view(
            template_name="registration/password_change_done.html"
        ),
        name="password_change_done",
    ),
    # Shared terminal account management
    path("terminals/", TerminalListView.as_view(), name="terminal-list"),
    path("terminals/add/", TerminalCreateView.as_view(), name="terminal-add"),
    path("terminals/<int:pk>/login/", TerminalLoginView.as_view(), name="terminal-login"),
    path("terminals/<int:pk>/edit/", TerminalUpdateView.as_view(), name="terminal-edit"),
    path(
        "terminals/<int:pk>/deactivate/",
        TerminalDeactivateView.as_view(),
        name="terminal-deactivate",
    ),
    path(
        "terminals/<int:pk>/reactivate/",
        TerminalReactivateView.as_view(),
        name="terminal-reactivate",
    ),
    # Public machine pages
    path("m/", PublicMachineListView.as_view(), name="public-machine-list"),
    path("m/<slug:slug>/", PublicMachineDetailView.as_view(), name="public-machine-detail"),
    # Problem report submission
    path(
        "p/<slug:slug>/",
        maintenance_views.ProblemReportCreateView.as_view(),
        name="problem-report-create",
    ),
    # Maintainer problem report views
    path(
        "problem-reports/",
        maintenance_views.ProblemReportListView.as_view(),
        name="problem-report-list",
    ),
    path(
        "problem-reports/entries/",
        maintenance_views.ProblemReportListPartialView.as_view(),
        name="problem-report-list-entries",
    ),
    path(
        "problem-reports/<int:pk>/",
        maintenance_views.ProblemReportDetailView.as_view(),
        name="problem-report-detail",
    ),
    path(
        "problem-reports/<slug:slug>/",
        maintenance_views.MachineProblemReportListView.as_view(),
        name="machine-problem-reports",
    ),
    # Maintainer machine views
    path("machines/", MachineListView.as_view(), name="maintainer-machine-list"),
    path("machines/new/", MachineQuickCreateView.as_view(), name="machine-quick-create"),
    path("machines/<slug:slug>/", MachineDetailView.as_view(), name="maintainer-machine-detail"),
    path(
        "machines/<slug:slug>/activity/",
        MachineActivityPartialView.as_view(),
        name="machine-activity-entries",
    ),
    path("machines/<slug:slug>/edit/", MachineUpdateView.as_view(), name="machine-edit"),
    path("machines/<slug:slug>/qr/", maintenance_views.MachineQRView.as_view(), name="machine-qr"),
    # Machine model editing
    path("models/<slug:slug>/edit/", MachineModelUpdateView.as_view(), name="machine-model-edit"),
    # API endpoints
    path(
        "api/transcoding/upload/",
        maintenance_views.ReceiveTranscodedMediaView.as_view(),
        name="api-transcoding-upload",
    ),
    path(
        "api/maintainers/",
        maintenance_views.MaintainerAutocompleteView.as_view(),
        name="api-maintainer-autocomplete",
    ),
    # Log views
    path("logs/", maintenance_views.LogListView.as_view(), name="log-list"),
    path("logs/entries/", maintenance_views.LogListPartialView.as_view(), name="log-list-entries"),
    path("logs/<int:pk>/", maintenance_views.LogEntryDetailView.as_view(), name="log-detail"),
    path(
        "logs/new/<slug:slug>/",
        maintenance_views.MachineLogCreateView.as_view(),
        name="log-create-machine",
    ),
    path(
        "logs/<slug:slug>/entries/",
        maintenance_views.MachineLogPartialView.as_view(),
        name="log-entries",
    ),
    path("logs/<slug:slug>/", maintenance_views.MachineLogView.as_view(), name="log-machine"),
]

media_url = settings.MEDIA_URL.lstrip("/")
if media_url:
    urlpatterns += [
        re_path(rf"^{media_url}(?P<path>.*)$", serve_media, name="media"),
    ]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
