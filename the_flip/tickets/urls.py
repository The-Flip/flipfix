from django.urls import path
from django.contrib.auth.views import LogoutView
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('reports/', views.report_list, name='report_list'),
    path('reports/<int:pk>/', views.report_detail, name='report_detail'),
    path('new_report/', views.report_create, name='report_create'),
    path('new_report/<slug:machine_slug>/', views.report_create, name='report_create_qr'),
    path('machines/', views.machine_list, name='machine_list'),
    path('machines/<slug:slug>/', views.machine_detail, name='machine_detail'),
    path('machines/<slug:slug>/qr/', views.machine_qr, name='machine_qr'),
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),

    # Backwards compatibility URLs (redirect old game URLs to machine URLs)
    path('games/', views.game_list, name='game_list'),
    path('games/<int:pk>/', views.game_detail, name='game_detail'),
    path('games/<int:pk>/qr/', views.game_qr, name='game_qr'),
]
