from django.urls import path
from . import views

urlpatterns = [
    # Auth Endpoints
    path('auth/register/user/', views.register_user_view, name='register_user'),
    path('auth/register/ngo/', views.register_ngo_view, name='register_ngo'),
    path('auth/login/', views.login_view, name='login'),
    path('auth/me/', views.me_view, name='me'),
    path('citizen/nearest-ngo/', views.nearest_ngo_view, name='nearest_ngo'),
    path('detect-location/', views.detect_location_view, name='detect_location'),
    path('reverse-geocode/', views.reverse_geocode_view, name='reverse_geocode'),
    path('public/ngos/', views.public_ngos_view, name='public_ngos'),
    
    # Emergency SOS Endpoints
    path('emergencies/', views.emergencies_view, name='emergencies'),
    path('emergencies/<str:sos_id>/', views.emergency_detail_view, name='emergency_detail'),
    path('emergencies/<str:sos_id>/nearby-ngos/', views.sos_nearby_ngos_view, name='emergency_nearby_ngos'),
    path('emergencies/<str:sos_id>/accept/', views.sos_accept_view, name='emergency_accept'),
    path('emergencies/<str:sos_id>/dispatch/', views.sos_dispatch_view, name='emergency_dispatch'),
    path('emergencies/<str:sos_id>/arrived/', views.sos_arrived_view, name='emergency_arrived'),
    path('emergencies/<str:sos_id>/resolve/', views.sos_resolve_view, name='emergency_resolve'),
    path('emergencies/<str:sos_id>/tracking/', views.sos_tracking_view, name='emergency_tracking'),
    path('rescue/<str:sos_id>/location/', views.rescue_location_update_view, name='rescue_location_update'),

    # SOS workflow aliases
    path('sos/', views.emergencies_view, name='sos_list'),
    path('sos/active/', views.sos_active_view, name='sos_active'),
    path('sos/history/', views.sos_history_view, name='sos_history'),
    path('sos/<str:sos_id>/', views.emergency_detail_view, name='sos_detail'),
    path('sos/<str:sos_id>/nearby-ngos/', views.sos_nearby_ngos_view, name='sos_nearby_ngos'),
    path('sos/<str:sos_id>/accept/', views.sos_accept_view, name='sos_accept'),
    path('sos/<str:sos_id>/dispatch/', views.sos_dispatch_view, name='sos_dispatch'),
    path('sos/<str:sos_id>/arrived/', views.sos_arrived_view, name='sos_arrived'),
    path('sos/<str:sos_id>/resolve/', views.sos_resolve_view, name='sos_resolve'),
    path('sos/<str:sos_id>/tracking/', views.sos_tracking_view, name='sos_tracking'),
    path('sos/<str:sos_id>/location/', views.rescue_location_update_view, name='sos_location_update'),
    
    # Showcase Ecosystem Endpoints
    path('matchmaker/', views.matchmaker_query_view, name='matchmaker'),
    path('active-tracking/', views.active_tracking_view, name='active_tracking'),
    path('alerts/', views.alerts_view, name='alerts'),
    path('donations/', views.donations_view, name='donations'),
    path('transmit-location/', views.transmit_location_view, name='transmit_location'),
    path('ngo-analytics/', views.ngo_analytics_view, name='ngo_analytics'),
    
    # System Admin Endpoints
    path('admin/stats/', views.admin_stats_view, name='admin_stats'),
    path('admin/ngos/', views.admin_ngos_view, name='admin_ngos'),
    path('admin/ngos/<int:ngo_id>/toggle-verify/', views.admin_ngo_toggle_verify_view, name='admin_ngo_toggle_verify'),
    path('admin/ngos/<int:ngo_id>/delete/', views.admin_ngo_delete_view, name='admin_ngo_delete'),
    path('admin/requests/<str:sos_id>/delete/', views.admin_request_delete_view, name='admin_request_delete'),
]
