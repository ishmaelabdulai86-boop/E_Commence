from django.contrib import admin
from .models import Analytics, UserActivity, SalesReport, DashboardWidget

@admin.register(Analytics)
class AnalyticsAdmin(admin.ModelAdmin):
    list_display = ['date', 'total_revenue', 'total_orders', 'new_customers', 'conversion_rate']
    list_filter = ['date']
    search_fields = ['date']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-date']

@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ['user', 'activity_type', 'url', 'created_at']
    list_filter = ['activity_type', 'created_at']
    search_fields = ['user__username', 'url']
    readonly_fields = ['created_at']
    ordering = ['-created_at']

@admin.register(SalesReport)
class SalesReportAdmin(admin.ModelAdmin):
    list_display = ['report_type', 'period_start', 'period_end', 'generated_by', 'generated_at']
    list_filter = ['report_type', 'generated_at']
    search_fields = ['generated_by__username']
    readonly_fields = ['generated_at']

@admin.register(DashboardWidget)
class DashboardWidgetAdmin(admin.ModelAdmin):
    list_display = ['title', 'widget_type', 'position', 'size', 'is_active']
    list_editable = ['position', 'size', 'is_active']
    list_filter = ['widget_type', 'is_active']
    ordering = ['position']