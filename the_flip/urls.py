"""
URL configuration for the_flip project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView

from the_flip.apps.catalog.views import (
    MachineDetailView,
    MachineListView,
    PublicMachineDetailView,
    PublicMachineListView,
)
from the_flip.apps.maintenance import views as maintenance_views
from django.contrib.auth import views as auth_views

urlpatterns = [
path("", RedirectView.as_view(pattern_name="problem-report-list", permanent=False), name="home"),
    path("admin/", admin.site.urls),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    # Public machine pages
    path("m/", PublicMachineListView.as_view(), name="public-machine-list"),
    path("m/<slug:slug>/", PublicMachineDetailView.as_view(), name="public-machine-detail"),

    # Problem report submission
    # path("p/", maintenance_views.ProblemReportCreateView.as_view(), name="problem-report-create-select-machine"),
    path("p/<slug:slug>/", maintenance_views.ProblemReportCreateView.as_view(), name="problem-report-create"),

    # Maintainer problem report views
    path("problem-reports/", maintenance_views.ProblemReportListView.as_view(), name="problem-report-list"),
    # path("problem-reports/<int:pk>/", maintenance_views.ProblemReportDetailView.as_view(), name="problem-report-detail"),

    # Maintainer machine views
    path("machines/", MachineListView.as_view(), name="maintainer-machine-list"),
    path("machines/<slug:slug>/", MachineDetailView.as_view(), name="maintainer-machine-detail"),
    # path("machines/<slug:slug>/qr/", maintenance_views.MachineQRView.as_view(), name="machine-qr"),

    # Log views
    path("logs/", maintenance_views.MachineLogView.as_view(), name="log-list"),
    path("logs/<int:pk>/", maintenance_views.LogEntryDetailView.as_view(), name="log-detail"),
    path("logs/new/<slug:slug>/", maintenance_views.MachineLogCreateView.as_view(), name="log-create-machine"),
    path("logs/<slug:slug>/entries/", maintenance_views.MachineLogPartialView.as_view(), name="log-entries"),
    path("logs/<slug:slug>/", maintenance_views.MachineLogView.as_view(), name="log-machine"),
    # path("logs/new/", maintenance_views.LogEntryCreateView.as_view(), name="log-create"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
