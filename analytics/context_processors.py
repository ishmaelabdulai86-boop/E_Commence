# analytics/context_processors.py
def admin_sidebar_context(request):
    """Add admin sidebar data to context"""
    context = {}
    
    if request.user.is_authenticated and (request.user.is_staff or getattr(request.user, 'role', '') in ['admin', 'seller']):
        from products.models import Product, ProductReview
        from orders.models import Order
        from django.db.models import F
        
        # Low stock products
        context['low_stock_count'] = Product.objects.filter(
            stock__lt=F('low_stock_threshold'), 
            stock__gt=0,
            is_active=True
        ).count()
        
        # Pending reviews
        context['pending_reviews_count'] = ProductReview.objects.filter(
            is_approved=False
        ).count()
        
        # Pending orders
        context['pending_orders_count'] = Order.objects.filter(
            status__in=['pending', 'processing']
        ).count()
        
        # Add status choices for templates
        from orders.models import Order
        context['order_status_choices'] = Order.ORDER_STATUS_CHOICES
        context['payment_status_choices'] = Order.PAYMENT_STATUS_CHOICES
        
    return context