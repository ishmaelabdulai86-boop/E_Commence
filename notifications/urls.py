from django.urls import path
from .import views

app_name = 'notifications'

urlpatterns = [
    # User notifications
    path('', views.notification_list, name='notification_list'),
    path('mark-read/<uuid:notification_id>/', views.mark_as_read, name='mark_as_read'),
    path('mark-all-read/', views.mark_all_as_read, name='mark_all_as_read'),
    
    # Preferences
    path('preferences/', views.notification_preferences, name='notification_preferences'),
    path('test/', views.test_notification, name='test_notification'),
    
    # Push Notifications
    path('push/register/', views.register_push_device, name='register_push_device'),
    path('push/unregister/', views.unregister_push_device, name='unregister_push_device'),
    path('push/subscribe/', views.web_push_subscribe, name='web_push_subscribe'),
    
    # API Endpoints
    path('api/unread-count/', views.get_unread_count, name='get_unread_count'),
    path('api/search-users/', views.api_search_users, name='api_search_users'),
    path('api/template-preview/<int:template_id>/', views.api_template_preview, name='api_template_preview'),
    path('api/retry-email/', views.api_retry_email, name='api_retry_email'),
    
    # Admin views - Use a different prefix to avoid conflict
    path('admin-dashboard/', views.admin_notification_dashboard, name='admin_notification_dashboard'),
    path('admin-notifications/', views.admin_notification_list, name='admin_notification_list'),
    path('admin-notifications/<uuid:notification_id>/', views.admin_notification_detail, name='admin_notification_detail'),
    path('admin-templates/', views.admin_template_list, name='admin_template_list'),
    path('admin-templates/add/', views.admin_template_add, name='admin_template_add'),  # This needs to come BEFORE detail
    path('admin-templates/<int:template_id>/', views.admin_template_detail, name='admin_template_detail'),
    path('admin-email-logs/', views.admin_email_logs, name='admin_email_logs'),
    path('admin-sms-logs/', views.admin_sms_logs, name='admin_sms_logs'),
    path('admin-preferences/', views.admin_preferences_list, name='admin_preferences_list'),
    path('admin-bulk-send/', views.admin_send_bulk_notification, name='admin_send_bulk_notification'),
    path('admin-test/', views.admin_test_notification, name='admin_test_notification'),
    path('admin-quick-test/', views.admin_quick_test, name='admin_quick_test'),
]