# context_processors.py
from payments.models import Refund
from django.db.models import Q

def admin_context(request):
    context = {}
    if request.user.is_authenticated and (request.user.is_staff or getattr(request.user, 'role', '') == 'admin'):
        context.update({
            'pending_refunds_count': Refund.objects.filter(
                Q(status='pending') | Q(status='processing')
            ).count(),
        })
    return context