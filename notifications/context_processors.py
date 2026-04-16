# notifications/context_processors.py
from .models import Notification
from django.utils import timezone
def notification_context(request):
    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
        recent_notifications = Notification.objects.filter(
            user=request.user
        ).order_by('-created_at')[:5]
        
        return {
            'unread_notifications_count': unread_count,
            'user_notifications': recent_notifications,
        }
    return {}

def admin_notification_context(request):
    """Add notification counts to admin context"""
    if request.user.is_authenticated and request.user.is_staff:
        return {
            'admin_unread_count': Notification.objects.filter(is_read=False).count(),
            'admin_failed_count': Notification.objects.filter(status='failed').count(),
            'admin_today_count': Notification.objects.filter(
                created_at__date=timezone.now().date()
            ).count(),
        }
    return {}