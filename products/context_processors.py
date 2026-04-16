# products/context_processors.py
from django.shortcuts import render
from .models import Category, Product


def categories_processor(request):
    categories = Category.objects.filter(is_active=True, parent=None)
    for cat in categories:
        cat.product_count = Product.objects.filter(category=cat, is_active=True).count()
    return {'all_categories': categories}
def category_list(request):
    categories = Category.objects.filter(is_active=True, parent=None)
    
    for cat in categories:
        cat.product_count = Product.objects.filter(category=cat, is_active=True).count()
    
    total_products = Product.objects.filter(is_active=True).count()
    
    context = {
        'categories': categories,
        'total_products': total_products,
    }
    
    return render(request, 'products/categories.html', context)

# Add this function to your views.py file (at the end)
def admin_sidebar_context(request):
    """Add admin sidebar data to context"""
    if request.user.is_authenticated and (request.user.is_staff or request.user.role in ['admin', 'seller']):
        from .models import Product, ProductReview
        from django.db.models import F
        
        low_stock_count = Product.objects.filter(
            stock__lte=F('low_stock_threshold'), 
            stock__gt=0
        ).count()
        
        pending_reviews_count = ProductReview.objects.filter(is_approved=False).count()
        
        return {
            'low_stock_count': low_stock_count,
            'pending_reviews_count': pending_reviews_count,
        }
    return {}