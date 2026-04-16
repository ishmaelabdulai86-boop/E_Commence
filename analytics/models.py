from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import date, timedelta
import json

class Analytics(models.Model):
    """Store aggregated analytics data"""
    date = models.DateField(unique=True)
    
    # Sales Metrics
    total_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_orders = models.IntegerField(default=0)
    total_items_sold = models.IntegerField(default=0)
    average_order_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Customer Metrics
    new_customers = models.IntegerField(default=0)
    returning_customers = models.IntegerField(default=0)
    
    # Product Metrics
    top_products = models.JSONField(default=list)  # List of top selling products
    
    # Traffic Metrics
    page_views = models.IntegerField(default=0)
    unique_visitors = models.IntegerField(default=0)
    bounce_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # Percentage
    
    # Conversion Metrics
    conversion_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # Percentage
    cart_abandonment_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # Percentage
    
    # Calculated Fields
    revenue_data = models.JSONField(default=dict)  # Hourly/daily breakdown
    category_data = models.JSONField(default=dict)  # Sales by category
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = 'Analytics'
        ordering = ['-date']
    
    def __str__(self):
        return f"Analytics for {self.date}"
    
    @classmethod
    def get_or_create_today(cls):
        today = date.today()
        obj, created = cls.objects.get_or_create(date=today)
        return obj

class UserActivity(models.Model):
    """Track user activities on the site"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    session_key = models.CharField(max_length=40, blank=True)
    
    activity_type = models.CharField(max_length=50)  # 'page_view', 'product_view', 'add_to_cart', etc.
    url = models.CharField(max_length=500)
    referrer = models.CharField(max_length=500, blank=True)
    
    # Product-related activities
    product = models.ForeignKey('products.Product', on_delete=models.SET_NULL, null=True, blank=True)
    category = models.ForeignKey('products.Category', on_delete=models.SET_NULL, null=True, blank=True)
    
    # Additional data
    metadata = models.JSONField(default=dict)
    
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['activity_type', 'created_at']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.user or 'Anonymous'} - {self.activity_type} at {self.created_at}"

class SalesReport(models.Model):
    """Generated sales reports"""
    REPORT_TYPE_CHOICES = [
        ('daily', 'Daily Report'),
        ('weekly', 'Weekly Report'),
        ('monthly', 'Monthly Report'),
        ('yearly', 'Yearly Report'),
        ('custom', 'Custom Report'),
    ]
    
    report_type = models.CharField(max_length=20, choices=REPORT_TYPE_CHOICES)
    period_start = models.DateField()
    period_end = models.DateField()
    
    # Report Data
    summary = models.JSONField(default=dict)
    sales_data = models.JSONField(default=dict)
    product_data = models.JSONField(default=dict)
    customer_data = models.JSONField(default=dict)
    
    # File Storage
    pdf_file = models.FileField(upload_to='reports/', blank=True)
    excel_file = models.FileField(upload_to='reports/', blank=True)
    
    generated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-generated_at']
    
    def __str__(self):
        return f"{self.get_report_type_display()} - {self.period_start} to {self.period_end}"

class DashboardWidget(models.Model):
    """Custom dashboard widgets configuration"""
    WIDGET_TYPE_CHOICES = [
        ('sales_chart', 'Sales Chart'),
        ('revenue_chart', 'Revenue Chart'),
        ('top_products', 'Top Products'),
        ('customer_stats', 'Customer Statistics'),
        ('conversion_funnel', 'Conversion Funnel'),
        ('geo_map', 'Geographic Map'),
    ]
    
    title = models.CharField(max_length=100)
    widget_type = models.CharField(max_length=50, choices=WIDGET_TYPE_CHOICES)
    position = models.IntegerField(default=0)
    size = models.CharField(max_length=20, default='medium')  # small, medium, large
    is_active = models.BooleanField(default=True)
    
    # Configuration
    config = models.JSONField(default=dict)
    
    # Permissions
    visible_to_roles = models.JSONField(default=list)  # List of roles that can see this widget
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['position']
    
    def __str__(self):
        return self.title