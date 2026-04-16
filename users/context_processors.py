# Create a new file: users/context_processors.py
from .models import User

def admin_sidebar_context(request):
    """Add admin sidebar context."""
    if request.user.is_authenticated and (request.user.is_staff or request.user.role in ['admin', 'seller']):
        return {
            'pending_users_count': User.objects.filter(is_active=False).count(),
            'unverified_users_count': User.objects.filter(email_verified=False).count(),
        }
    return {}