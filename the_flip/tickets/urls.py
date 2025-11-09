from django.urls import path
from django.contrib.auth.views import LogoutView
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('reports/', views.report_list, name='report_list'),
    path('reports/<int:pk>/', views.report_detail, name='report_detail'),
    path('new_report/', views.report_create, name='report_create'),
    path('new_report/<int:game_id>/', views.report_create, name='report_create_qr'),
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
]
