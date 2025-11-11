from django.urls import path
from django.contrib.auth.views import LogoutView
from . import views

urlpatterns = [
    path('', views.home, name='home'),

    # Visitor URLs (public access)
    path('m/<slug:slug>/', views.machine_public_view, name='machine_public'),
    path('p/<slug:slug>/', views.problem_report_create, name='problem_report_create'),

    # Global task URLs (maintainers only)
    path('tasks/', views.report_list, name='task_list'),
    path('tasks/<int:pk>/', views.report_detail, name='task_detail'),
    path('tasks/new/', views.task_create_todo, name='task_create_todo'),

    # Machine-scoped URLs (maintainers only)
    path('machines/', views.machine_list, name='machine_list'),
    path('machines/<slug:slug>/', views.machine_detail, name='machine_detail'),
    path('machines/<slug:slug>/tasks/', views.machine_tasks_list, name='machine_tasks_list'),
    path('machines/<slug:slug>/tasks2/', views.machine_tasks_list_v2, name='machine_tasks_list_v2'),
    path('machines/<slug:slug>/tasks/new/', views.machine_task_create, name='machine_task_create'),
    path('machines/<slug:slug>/log/', views.machine_log_list, name='machine_log_list'),
    path('machines/<slug:slug>/log/<int:pk>/', views.machine_log_detail, name='machine_log_detail'),
    path('machines/<slug:slug>/log/new/', views.machine_log_create, name='machine_log_create'),
    path('machines/<slug:slug>/qr/', views.machine_qr, name='machine_qr'),

    # Auth
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
]
