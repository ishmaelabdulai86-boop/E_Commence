from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.db.models import Sum, Count, Avg, Q, F, Max
from django.utils import timezone
from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta
import json
from decimal import Decimal

from orders.models import Order, OrderItem
from users.models import User
from products.models import Product, Category
from .models import Analytics, UserActivity, SalesReport, DashboardWidget

from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from datetime import timedelta, datetime
from django.db.models import Sum, Count, Avg
from orders.models import Order, OrderItem
from products.models import Product,ProductReview
from django.contrib.auth import get_user_model

User = get_user_model()


def is_admin_or_staff(user):
    """Check if user is admin or staff"""
    return user.is_authenticated and (user.is_staff or user.is_superuser or user.role in ['admin', 'seller'])

def admin_required(view_func):
    """Decorator to check if user is admin/staff"""
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser or request.user.role in ['admin', 'seller']):
            return view_func(request, *args, **kwargs)
        else:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
    return wrapper

# ==================== MAIN ADMIN DASHBOARD ====================

@login_required
@admin_required
def admin_dashboard(request):
    """Main admin dashboard - this is the entry point for all admin functions"""
    
    # Date ranges
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    year_ago = today - timedelta(days=365)
    
    # TODAY'S STATS
    today_orders = Order.objects.filter(created_at__date=today)
    today_revenue = today_orders.aggregate(total=Sum('total_amount'))['total'] or 0
    today_order_count = today_orders.count()
    
    # Get today's paid orders
    today_paid_orders = Order.objects.filter(
        created_at__date=today,
        payment_status='paid'
    )
    today_paid_revenue = today_paid_orders.aggregate(total=Sum('total_amount'))['total'] or 0
    
    # WEEKLY STATS
    week_orders = Order.objects.filter(created_at__date__gte=week_ago)
    week_revenue = week_orders.aggregate(total=Sum('total_amount'))['total'] or 0
    week_order_count = week_orders.count()
    
    # MONTHLY STATS
    month_orders = Order.objects.filter(created_at__date__gte=month_ago)
    month_revenue = month_orders.aggregate(total=Sum('total_amount'))['total'] or 0
    month_order_count = month_orders.count()
    
    # USER STATS
    total_users = User.objects.count()
    new_users_today = User.objects.filter(date_joined__date=today).count()
    
    # PRODUCT STATS
    total_products = Product.objects.filter(is_active=True).count()
    low_stock_products = Product.objects.filter(
        stock__lte=F('low_stock_threshold'),
        stock__gt=0,
        is_active=True
    ).count()
    out_of_stock_products = Product.objects.filter(stock=0, is_active=True).count()
    
    # REVIEW STATS
    pending_reviews = ProductReview.objects.filter(is_approved=False).count()
    
    # RECENT ORDERS
    recent_orders = Order.objects.select_related('user').order_by('-created_at')[:10]
    
    # TOP SELLING PRODUCTS
    top_products = OrderItem.objects.filter(
        order__created_at__date__gte=week_ago,
        order__payment_status='paid'
    ).values(
        'product__name', 
        'product__sku'
    ).annotate(
        total_sold=Sum('quantity'),
        revenue=Sum(F('quantity') * F('unit_price'))
    ).order_by('-total_sold')[:5]
    
    # LOW STOCK PRODUCTS
    low_stock_items = Product.objects.filter(
        stock__lte=F('low_stock_threshold'),
        stock__gt=0,
        is_active=True
    ).order_by('stock')[:5]
    
    # PENDING REVIEWS
    pending_review_items = ProductReview.objects.filter(
        is_approved=False
    ).select_related('product', 'user').order_by('-created_at')[:5]
    
    # ORDER STATUS DISTRIBUTION
    order_status = Order.objects.filter(
        created_at__date__gte=month_ago
    ).values('status').annotate(
        count=Count('id'),
        revenue=Sum('total_amount')
    ).order_by('status')
    
    # REVENUE CHART DATA (Last 30 days)
    revenue_data = []
    for i in range(29, -1, -1):
        day = today - timedelta(days=i)
        daily_revenue = Order.objects.filter(
            created_at__date=day,
            payment_status='paid'
        ).aggregate(revenue=Sum('total_amount'))['revenue'] or 0
        
        revenue_data.append({
            'date': day.strftime('%Y-%m-%d'),
            'revenue': float(daily_revenue)
        })
    
    context = {
        # Dashboard stats
        'today_revenue': today_revenue,
        'today_paid_revenue': today_paid_revenue,
        'today_order_count': today_order_count,
        'week_revenue': week_revenue,
        'week_order_count': week_order_count,
        'month_revenue': month_revenue,
        'month_order_count': month_order_count,
        
        # User stats
        'total_users': total_users,
        'new_users_today': new_users_today,
        
        # Product stats
        'total_products': total_products,
        'low_stock_products': low_stock_products,
        'out_of_stock_products': out_of_stock_products,
        'pending_reviews': pending_reviews,
        
        # Lists
        'recent_orders': recent_orders,
        'top_products': top_products,
        'low_stock_items': low_stock_items,
        'pending_review_items': pending_review_items,
        'order_status': order_status,
        
        # Chart data
        'revenue_data': json.dumps(revenue_data),
        
        # For template
        'today': today,
        'week_ago': week_ago,
        'month_ago': month_ago,
    }
    
    return render(request, 'analytics/admin_dashboard.html', context)

def staff_required(view_func):
    """Decorator to check if user is staff"""
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_staff:
            return view_func(request, *args, **kwargs)
        else:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
    return wrapper


def admin_sidebar_context(request):
    """Add admin sidebar data to context"""
    if request.user.is_authenticated and (request.user.is_staff or request.user.role in ['admin', 'seller']):
        from .models import Product, ProductReview
        from django.db.models import F
        
        low_stock_count = Product.objects.filter(
            stock__lte=F('low_stock_threshold'), 
            stock__gt=0,
            is_active=True
        ).count()
        
        pending_reviews_count = ProductReview.objects.filter(is_approved=False).count()
        
        return {
            'low_stock_count': low_stock_count,
            'pending_reviews_count': pending_reviews_count,
        }
    return {}

def is_admin_or_staff(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser or user.role == 'admin')

@login_required
@user_passes_test(is_admin_or_staff)
def analytics_dashboard(request):
    """Main analytics dashboard"""
    
    # Date ranges
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    year_ago = today - timedelta(days=365)
    
    # Get period from request
    period = request.GET.get('period', '30d')
    if period == '7d':
        days = 7
    elif period == '30d':
        days = 30
    elif period == '90d':
        days = 90
    elif period == '1y':
        days = 365
    else:
        days = 30
    
    # Today's sales
    today_orders = Order.objects.filter(
        created_at__date=today,
        payment_status='paid'
    )
    today_revenue = today_orders.aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0')
    today_order_count = today_orders.count()
    today_avg_order = today_orders.aggregate(Avg('total_amount'))['total_amount__avg'] or Decimal('0')
    
    today_sales = {
        'revenue': today_revenue,
        'orders': today_order_count,
        'avg_order': today_avg_order
    }
    
    # Week's sales
    week_orders = Order.objects.filter(
        created_at__date__gte=week_ago,
        payment_status='paid'
    )
    week_revenue = week_orders.aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0')
    week_order_count = week_orders.count()
    
    week_sales = {
        'revenue': week_revenue,
        'orders': week_order_count
    }
    
    # Month's sales
    month_orders = Order.objects.filter(
        created_at__date__gte=month_ago,
        payment_status='paid'
    )
    month_revenue = month_orders.aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0')
    month_order_count = month_orders.count()
    
    month_sales = {
        'revenue': month_revenue,
        'orders': month_order_count
    }
    
    # Year's sales
    year_orders = Order.objects.filter(
        created_at__date__gte=year_ago,
        payment_status='paid'
    )
    year_revenue = year_orders.aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0')
    
    # Customer data
    total_customers = User.objects.filter(role='customer').count()
    new_customers_today = User.objects.filter(
        date_joined__date=today,
        role='customer'
    ).count()
    
    active_customers = User.objects.filter(
        orders__created_at__date__gte=month_ago,
        role='customer'
    ).distinct().count()
    
    # Top products
    top_products = OrderItem.objects.filter(
        order__created_at__date__gte=month_ago,
        order__payment_status='paid'
    ).values(
        'product__name', 
        'product__sku',
        'product__category__name'
    ).annotate(
        total_sold=Sum('quantity'),
        revenue=Sum(F('quantity') * F('unit_price')),
        avg_price=Avg('unit_price')
    ).order_by('-revenue')[:10]
    
    # Category sales
    category_sales = OrderItem.objects.filter(
        order__created_at__date__gte=month_ago,
        order__payment_status='paid'
    ).values('product__category__name').annotate(
        revenue=Sum(F('quantity') * F('unit_price'))
    ).order_by('-revenue')
    
    # REVENUE TREND DATA (Last X days based on period)
    revenue_data = []
    for i in range(days, -1, -1):
        day = today - timedelta(days=i)
        
        daily_orders = Order.objects.filter(
            created_at__date=day,
            payment_status='paid'
        )
        
        daily_revenue = daily_orders.aggregate(
            revenue=Sum('total_amount')
        )['revenue'] or Decimal('0')
        
        daily_order_count = daily_orders.count()
        
        # Format date for chart
        if days <= 30:
            date_label = day.strftime('%d %b')  # "01 Feb" format for short periods
        else:
            date_label = day.strftime('%b %Y')  # "Feb 2026" for longer periods
        
        revenue_data.append({
            'date': date_label,
            'revenue': float(daily_revenue),
            'orders': daily_order_count,
            'full_date': day.strftime('%Y-%m-%d')
        })
        
        
    
    # ORDER STATUS DISTRIBUTION
    order_status_counts = Order.objects.filter(
        created_at__date__gte=month_ago
    ).values('status').annotate(
        count=Count('id'),
        revenue=Sum('total_amount')
    ).order_by('-count')
    
    # RECENT ORDERS (last 10 orders)
    recent_orders = Order.objects.select_related('user').prefetch_related('items').filter(
        payment_status='paid'
    ).order_by('-created_at')[:10]
    for product in top_products:
        try:
            product_obj = Product.objects.get(id=product['product__id'])
            product['image_url'] = product_obj.image.url if product_obj.image else None
            product['product_url'] = product_obj.get_absolute_url()
        except:
            product['image_url'] = None
            product['product_url'] = '#'
    # Prepare context for template
    context = {
        # Sales metrics
        'today_sales': today_sales,
        'week_sales': week_sales,
        'month_sales': month_sales,
        'year_sales': {'revenue': year_revenue},
        
        # Customer metrics
        'total_customers': total_customers,
        'new_customers_today': new_customers_today,
        'active_customers': active_customers,
        
        # Product metrics
        'top_products': top_products,
        'category_sales': category_sales,
        
        # Charts data
        'revenue_data': revenue_data,  # Pass as list of dicts, not JSON
        'order_status_counts': order_status_counts,
        
        # Recent data
        'recent_orders': recent_orders,
        
        # Period info
        'period': period,
        'today': today,
        'week_ago': week_ago,
        'month_ago': month_ago,
        'year_ago': year_ago,
    }
    
    return render(request, 'admin/dashboard.html', context)


@login_required
@user_passes_test(is_admin_or_staff)
def sales_report(request):
    """Generate and view sales reports"""
    
    # Default period (last 30 days)
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=30)
    
    if request.method == 'POST':
        start_date = datetime.strptime(request.POST.get('start_date'), '%Y-%m-%d').date()
        end_date = datetime.strptime(request.POST.get('end_date'), '%Y-%m-%d').date()
        report_type = request.POST.get('report_type', 'custom')
    
    # Get orders in period
    orders = Order.objects.filter(
        created_at__date__range=[start_date, end_date],
        payment_status='paid'
    ).select_related('user').prefetch_related('items')
    
    # Calculate metrics
    total_revenue = orders.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    total_orders = orders.count()
    total_items = OrderItem.objects.filter(order__in=orders).aggregate(Sum('quantity'))['quantity__sum'] or 0
    avg_order_value = total_revenue / total_orders if total_orders > 0 else 0
    
    # Customer metrics
    customers = User.objects.filter(
        orders__created_at__date__range=[start_date, end_date]
    ).distinct()
    new_customers = customers.filter(date_joined__date__range=[start_date, end_date]).count()
    
    # Product performance
    top_products = OrderItem.objects.filter(
        order__in=orders
    ).values(
        'product__name',
        'product__sku',
        'product__category__name'
    ).annotate(
        quantity_sold=Sum('quantity'),
        revenue=Sum(F('quantity') * F('unit_price'))
    ).order_by('-revenue')[:20]
    
    # Daily breakdown
    daily_sales = []
    current_date = start_date
    while current_date <= end_date:
        daily_orders = orders.filter(created_at__date=current_date)
        daily_revenue = daily_orders.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        daily_count = daily_orders.count()
        daily_avg_order_value = daily_revenue / daily_count if daily_count > 0 else 0
        
        daily_sales.append({
            'date': current_date,
            'revenue': daily_revenue,
            'orders': daily_count,
            'avg_order_value': daily_avg_order_value,
        })
        
        current_date += timedelta(days=1)
    
    # Payment method distribution
    payment_methods = orders.values('payment_method').annotate(
        count=Count('id'),
        revenue=Sum('total_amount')
    ).order_by('-revenue')
    
    context = {
        'start_date': start_date,
        'end_date': end_date,
        'total_revenue': total_revenue,
        'total_orders': total_orders,
        'total_items': total_items,
        'avg_order_value': avg_order_value,
        'new_customers': new_customers,
        'top_products': top_products,
        'daily_sales': daily_sales,
        'payment_methods': payment_methods,
        'orders': orders[:50],  # Recent orders for detail view
    }
    
    return render(request, 'admin/analytics/sales_report.html', context)

@login_required
@user_passes_test(is_admin_or_staff)
def customer_analytics(request):
    """Customer analytics view"""
    # Get all users with orders
    users_with_orders = User.objects.filter(
        orders__isnull=False
    ).distinct().annotate(
        order_count=Count('orders'),
        total_spent=Sum('orders__total_amount'),
        avg_order_value=Avg('orders__total_amount')
    )
    
    # Fix: Use positive indexing for first/last orders
    for user in users_with_orders:
        # Get first order
        first_order = user.orders.order_by('created_at').first()
        user.first_order_date = first_order.created_at if first_order else None
        
        # Get last order  
        last_order = user.orders.order_by('-created_at').first()
        user.last_order_date = last_order.created_at if last_order else None
    
    # Total customers
    total_customers = User.objects.count()
    
    # High-value customers (spent > $1000)
    high_value_customers_data = []
    for user in users_with_orders:
        if user.total_spent and user.total_spent > 1000:
            user_data = {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'order_count': user.order_count or 0,
                'total_spent': user.total_spent or 0,
                'first_order_date': user.first_order_date,
                'last_order_date': user.last_order_date,
            }
            high_value_customers_data.append(user_data)
    
    # Customer segmentation
    customer_segments = [
        {'segment': 'New (0-30 days)', 'count': User.objects.filter(
            date_joined__gte=timezone.now() - timedelta(days=30)
        ).count()},
        {'segment': 'Occasional (1-2 orders)', 'count': User.objects.filter(
            orders__isnull=False
        ).annotate(
            order_count=Count('orders')
        ).filter(
            order_count__range=[1, 2]
        ).count()},
        {'segment': 'Regular (3-10 orders)', 'count': User.objects.filter(
            orders__isnull=False
        ).annotate(
            order_count=Count('orders')
        ).filter(
            order_count__range=[3, 10]
        ).count()},
        {'segment': 'Loyal (10+ orders)', 'count': User.objects.filter(
            orders__isnull=False
        ).annotate(
            order_count=Count('orders')
        ).filter(
            order_count__gt=10
        ).count()},
    ]
    
    # Customer acquisition data (last 6 months)
    acquisition_data = []
    for i in range(5, -1, -1):
        month_start = timezone.now() - timedelta(days=30*i)
        month_end = month_start + timedelta(days=30)
        
        new_customers = User.objects.filter(
            date_joined__gte=month_start,
            date_joined__lt=month_end
        ).count()
        
        acquisition_data.append({
            'month': month_start.strftime('%b %Y'),
            'new_customers': new_customers
        })
    
    # Retention data (active customers per month)
    retention_data = []
    for i in range(5, -1, -1):
        month_start = timezone.now() - timedelta(days=30*i)
        month_end = month_start + timedelta(days=30)
        
        active_customers = User.objects.filter(
            orders__created_at__gte=month_start,
            orders__created_at__lt=month_end
        ).distinct().count()
        
        retention_data.append({
            'month': month_start.strftime('%b %Y'),
            'customers': active_customers
        })
    
    context = {
        'total_customers': total_customers,
        'high_value_customers': high_value_customers_data, 
        'customer_segments': customer_segments,
        'acquisition_data': json.dumps(acquisition_data),
        'retention_data': json.dumps(retention_data),
    }
    
    return render(request, 'admin/analytics/customer_analytics.html', context)


@login_required
@user_passes_test(is_admin_or_staff)
def product_analytics(request):
    """Product performance and inventory analytics"""
    
    # Top selling products
    top_selling = OrderItem.objects.filter(
        order__payment_status='paid',
        order__created_at__date__gte=timezone.now().date() - timedelta(days=30)
    ).values(
        'product__id',
        'product__name',
        'product__sku',
        'product__category__name'
    ).annotate(
        units_sold=Sum('quantity'),
        revenue=Sum(F('quantity') * F('unit_price')),
        avg_price=Avg('unit_price')
    ).order_by('-revenue')[:20]
    
    # Product categories performance
    category_performance = OrderItem.objects.filter(
        order__payment_status='paid',
        order__created_at__date__gte=timezone.now().date() - timedelta(days=30)
    ).values('product__category__name').annotate(
        units_sold=Sum('quantity'),
        revenue=Sum(F('quantity') * F('unit_price')),
        product_count=Count('product', distinct=True)
    ).order_by('-revenue')
    
    # Inventory analysis
    low_stock_products = Product.objects.filter(
        stock__lt=F('low_stock_threshold'),
        is_active=True
    ).order_by('stock')[:20]
    
    out_of_stock_products = Product.objects.filter(
        stock=0,
        is_active=True
    ).count()
    
    # Product conversion rates (views to purchases)
    # This would require tracking product views
    
    context = {
        'top_selling': top_selling,
        'category_performance': category_performance,
        'low_stock_products': low_stock_products,
        'out_of_stock_products': out_of_stock_products,
    }
    
    return render(request, 'admin/analytics/product_analytics.html', context)

@login_required
@user_passes_test(is_admin_or_staff)
def api_sales_data(request):
    """API endpoint for sales chart data"""
    
    period = request.GET.get('period', '30d')
    
    if period == '7d':
        days = 7
    elif period == '30d':
        days = 30
    elif period == '90d':
        days = 90
    elif period == '1y':
        days = 365
    else:
        days = 30
    
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=days)
    
    # Get daily sales
    daily_sales = []
    for i in range(days, -1, -1):
        date = end_date - timedelta(days=i)
        
        revenue = Order.objects.filter(
            created_at__date=date,
            payment_status='paid'
        ).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        
        orders = Order.objects.filter(
            created_at__date=date,
            payment_status='paid'
        ).count()
        
        daily_sales.append({
            'date': date.strftime('%Y-%m-%d'),
            'revenue': float(revenue),
            'orders': orders,
        })
    
    return JsonResponse({
        'success': True,
        'data': daily_sales,
        'period': period,
    })

@login_required
@user_passes_test(is_admin_or_staff)
def export_report(request, report_type):
    """Export analytics report to CSV or PDF"""
    
    from django.http import HttpResponse
    import csv
    from io import StringIO
    
    if report_type == 'sales_csv':
        # Generate CSV sales report
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="sales_report.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['Date', 'Order ID', 'Customer', 'Product', 'Quantity', 'Unit Price', 'Total', 'Payment Method'])
        
        # Last 30 days of orders
        orders = Order.objects.filter(
            created_at__date__gte=timezone.now().date() - timedelta(days=30),
            payment_status='paid'
        ).select_related('user').prefetch_related('items')
        
        for order in orders:
            for item in order.items.all():
                writer.writerow([
                    order.created_at.strftime('%Y-%m-%d'),
                    order.order_number,
                    order.user.username,
                    item.product_name,
                    item.quantity,
                    item.unit_price,
                    item.total_price,
                    order.payment_method,
                ])
        
        return response
    
    elif report_type == 'customers_csv':
        # Generate CSV customer report
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="customers_report.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['Customer ID', 'Username', 'Email', 'Join Date', 'Total Orders', 'Total Spent', 'Last Order Date'])
        
        customers = User.objects.filter(role='customer').annotate(
            total_orders=Count('orders'),
            total_spent=Sum('orders__total_amount'),
            last_order=Max('orders__created_at')
        ).order_by('-total_spent')
        
        for customer in customers:
            writer.writerow([
                customer.id,
                customer.username,
                customer.email,
                customer.date_joined.strftime('%Y-%m-%d'),
                customer.total_orders or 0,
                customer.total_spent or 0,
                customer.last_order.strftime('%Y-%m-%d') if customer.last_order else '',
            ])
        
        return response
    
    return HttpResponse('Invalid report type', status=400)