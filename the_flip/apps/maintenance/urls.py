from django.urls import path

from . import views

app_name = "maintenance"

urlpatterns = [
    path("", views.MaintenanceIndexView.as_view(), name="maintenance-index"),
    path("problem-reports/", views.ProblemReportListView.as_view(), name="problem-report-list"),
    path(
        "<slug:slug>/submit-problem-report/",
        views.ProblemReportCreateView.as_view(),
        name="problem-report-create",
    ),
    path(
        "<slug:slug>/log/",
        views.MachineLogView.as_view(),
        name="machine-log",
    ),
    path(
        "<slug:slug>/log/new/",
        views.MachineLogCreateView.as_view(),
        name="machine-log-create",
    ),
]
