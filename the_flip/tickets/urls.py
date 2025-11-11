from django.urls import path
from django.contrib.auth.views import LogoutView
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('m/<slug:slug>/', views.machine_public_view, name='machine_public'),
    path('tasks/', views.report_list, name='task_list'),
    path('tasks/<int:pk>/', views.report_detail, name='task_detail'),
    path('tasks/new/', views.report_create, name='task_create'),
    path('tasks/new/<slug:machine_slug>/', views.report_create, name='task_create_qr'),
    path('tasks/todo/new/', views.task_create_todo, name='task_create_todo'),
    path('machines/', views.machine_list, name='machine_list'),
    path('machines/<slug:slug>/', views.machine_detail, name='machine_detail'),
    path('machines/<slug:slug>/qr/', views.machine_qr, name='machine_qr'),
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
]
