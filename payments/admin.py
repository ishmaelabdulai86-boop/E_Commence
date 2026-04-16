import csv
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import Payment, Refund, PaymentGatewayConfig, TransactionLog
from django.http import HttpResponse
from django.db import models
# Removed accidental GeoDjango import; use standard Django models

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        'payment_id', 'user', 'amount', 'currency', 'payment_method',
        'status', 'is_successful', 'created_at', 'admin_actions'
    ]
    list_filter = ['status', 'payment_method', 'payment_gateway', 'created_at']
    search_fields = ['payment_id', 'user__username', 'user__email', 'gateway_transaction_id']
    readonly_fields = ['created_at', 'updated_at', 'paid_at', 'payment_id']
    list_per_page = 20
    
    fieldsets = (
        ('Payment Information', {
            'fields': ('payment_id', 'user', 'order', 'amount', 'currency')
        }),
        ('Payment Method', {
            'fields': ('payment_method', 'payment_gateway', 'status', 'is_successful')
        }),
        ('Customer Information', {
            'fields': ('customer_email', 'customer_phone', 'billing_address')
        }),
        ('Gateway Details', {
            'fields': ('gateway_transaction_id', 'gateway_response', 'gateway_error')
        }),
        ('Dates', {
            'fields': ('created_at', 'updated_at', 'paid_at')
        }),
        ('Metadata', {
            'fields': ('metadata',),
            'classes': ('collapse',),
        }),
    )
    
    def admin_actions(self, obj):
        """Admin actions column with HTML buttons"""
        actions_html = []
        
        # View action
        view_url = reverse('admin:payments_payment_change', args=[obj.id])
        actions_html.append(
            f'<a href="{view_url}" class="button" style="padding: 2px 8px; margin-right: 5px;">View</a>'
        )
        
        # Refund action (only for successful payments)
        if obj.is_successful and obj.status == 'completed':
            refund_url = reverse('admin:payments_refund_add') + f'?payment={obj.id}'
            actions_html.append(
                f'<a href="{refund_url}" class="button" style="background: #ffc107; padding: 2px 8px;">Refund</a>'
            )
        
        # Mark as paid action (for pending payments)
        elif obj.status == 'pending':
            mark_paid_url = reverse('admin:payments_payment_mark_paid', args=[obj.id])
            actions_html.append(
                f'<a href="{mark_paid_url}" class="button" style="background: #28a745; color: white; padding: 2px 8px;">Mark Paid</a>'
            )
        
        return format_html(''.join(actions_html))
    
    actions = ['export_as_csv']
    
    def export_as_csv(self, request, queryset):
        """Export selected payments as CSV"""
        meta = self.model._meta
        field_names = [field.name for field in meta.fields]
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename={meta}.csv'
        
        writer = csv.writer(response)
        writer.writerow(field_names)
        for obj in queryset:
            writer.writerow([getattr(obj, field) for field in field_names])
        
        return response
    
    export_as_csv.short_description = "Export selected payments to CSV"
    
    admin_actions.short_description = 'Actions'
    admin_actions.allow_tags = True
    
    def get_urls(self):
        """Add custom URLs for admin actions"""
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path('<path:object_id>/mark-paid/', self.mark_paid_view, name='payments_payment_mark_paid'),
        ]
        return custom_urls + urls
    
    def mark_paid_view(self, request, object_id):
        """Custom view to mark payment as paid"""
        from django.shortcuts import redirect
        from django.contrib import messages
        
        payment = Payment.objects.get(id=object_id)
        payment.mark_as_paid()
        payment.save()
        
        messages.success(request, f'Payment {payment.payment_id} marked as paid.')
        return redirect('admin:payments_payment_change', object_id=object_id)

@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = [
        'refund_id', 'payment_link', 'amount', 'currency', 'reason',
        'status', 'is_completed', 'requested_at', 'refund_actions'
    ]
    list_filter = ['status', 'reason', 'requested_at', 'is_completed']
    search_fields = ['refund_id', 'payment__payment_id', 'payment__order__order_number']
    readonly_fields = ['requested_at', 'processed_at', 'refund_id']
    list_editable = ['status']
    list_per_page = 20
    
    fieldsets = (
        ('Refund Information', {
            'fields': ('refund_id', 'payment', 'order', 'amount', 'currency')
        }),
        ('Refund Details', {
            'fields': ('reason', 'description', 'status', 'is_completed')
        }),
        ('Gateway Details', {
            'fields': ('gateway_refund_id', 'gateway_response', 'gateway_error')
        }),
        ('Request Information', {
            'fields': ('requested_by', 'requested_at', 'processed_at')
        }),
    )
    
    def payment_link(self, obj):
        """Display payment as a clickable link"""
        if obj.payment:
            url = reverse('admin:payments_payment_change', args=[obj.payment.id])
            return format_html('<a href="{}">{}</a>', url, obj.payment.payment_id)
        return '-'
    payment_link.short_description = 'Payment'
    payment_link.admin_order_field = 'payment__payment_id'
    
    def refund_actions(self, obj):
        """Admin actions for refunds"""
        actions_html = []
        
        # View action
        view_url = reverse('admin:payments_refund_change', args=[obj.id])
        actions_html.append(
            f'<a href="{view_url}" class="button" style="padding: 2px 8px; margin-right: 5px;">View</a>'
        )
        
        # Mark as completed action
        if not obj.is_completed and obj.status == 'processing':
            mark_completed_url = reverse('admin:payments_refund_mark_completed', args=[obj.id])
            actions_html.append(
                f'<a href="{mark_completed_url}" class="button" style="background: #28a745; color: white; padding: 2px 8px;">Complete</a>'
            )
        
        return format_html(''.join(actions_html))
    
    refund_actions.short_description = 'Actions'
    refund_actions.allow_tags = True
    
    def get_urls(self):
        """Add custom URLs for refund actions"""
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path('<path:object_id>/mark-completed/', self.mark_completed_view, name='payments_refund_mark_completed'),
        ]
        return custom_urls + urls
    
    def mark_completed_view(self, request, object_id):
        """Custom view to mark refund as completed"""
        from django.shortcuts import redirect
        from django.contrib import messages
        
        refund = Refund.objects.get(id=object_id)
        refund.mark_as_completed()
        refund.save()
        
        messages.success(request, f'Refund {refund.refund_id} marked as completed.')
        return redirect('admin:payments_refund_change', object_id=object_id)
    
    def get_form(self, request, obj=None, **kwargs):
        """Pre-select payment in refund form if payment_id is in query params"""
        form = super().get_form(request, obj, **kwargs)
        
        # Pre-select payment if payment_id is in query params
        payment_id = request.GET.get('payment')
        if payment_id and not obj:
            try:
                payment = Payment.objects.get(id=payment_id)
                form.base_fields['payment'].initial = payment
                form.base_fields['order'].initial = payment.order
                form.base_fields['amount'].initial = payment.amount
                form.base_fields['currency'].initial = payment.currency
            except Payment.DoesNotExist:
                pass
        
        return form

@admin.register(PaymentGatewayConfig)
class PaymentGatewayConfigAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'display_name', 'is_active', 'is_test_mode', 
        'transaction_fee_percent', 'is_configured', 'created_at'
    ]
    list_editable = ['is_active', 'is_test_mode', 'transaction_fee_percent']
    list_filter = ['is_active', 'is_test_mode', 'name']
    search_fields = ['name', 'display_name']
    readonly_fields = ['created_at', 'updated_at']
    list_per_page = 20
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'display_name', 'is_active', 'is_test_mode')
        }),
        ('API Credentials', {
            'fields': ('api_key', 'secret_key', 'webhook_secret'),
            'classes': ('collapse',),
        }),
        ('Configuration', {
            'fields': ('supported_currencies', 'supported_countries', 'payment_methods')
        }),
        ('Fees', {
            'fields': ('transaction_fee_percent', 'transaction_fee_fixed')
        }),
        ('Additional Configuration', {
            'fields': ('config_data',),
            'classes': ('collapse',),
        }),
    )
    
    def is_configured(self, obj):
        """Check if gateway is properly configured"""
        if obj.name in ['stripe', 'paystack', 'flutterwave']:
            return bool(obj.secret_key)
        elif obj.name == 'paypal':
            return bool(obj.api_key and obj.secret_key)
        return True
    is_configured.boolean = True
    is_configured.short_description = 'Configured'

@admin.register(TransactionLog)
class TransactionLogAdmin(admin.ModelAdmin):
    list_display = [
        'gateway', 'transaction_type', 'is_successful', 'duration_ms', 
        'created_at', 'view_details'
    ]
    list_filter = ['gateway', 'transaction_type', 'is_successful', 'created_at']
    search_fields = ['gateway', 'transaction_type', 'error_message']
    readonly_fields = ['created_at', 'gateway', 'transaction_type', 'request_data', 
                      'response_data', 'headers', 'is_successful', 'error_message', 
                      'duration_ms']
    list_per_page = 50
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Transaction Information', {
            'fields': ('gateway', 'transaction_type', 'is_successful', 'duration_ms')
        }),
        ('Request Data', {
            'fields': ('request_data',),
            'classes': ('collapse',),
        }),
        ('Response Data', {
            'fields': ('response_data',),
            'classes': ('collapse',),
        }),
        ('Headers', {
            'fields': ('headers',),
            'classes': ('collapse',),
        }),
        ('Error Information', {
            'fields': ('error_message',),
            'classes': ('collapse',),
        }),
        ('Timestamp', {
            'fields': ('created_at',)
        }),
    )
    
    def view_details(self, obj):
        """Link to view transaction details"""
        url = reverse('admin:payments_transactionlog_change', args=[obj.id])
        return format_html('<a href="{}" class="button">View</a>', url)
    view_details.short_description = 'Details'
    
    def has_add_permission(self, request):
        """Prevent adding transaction logs manually"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Prevent editing transaction logs"""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Allow deletion of transaction logs"""
        return True  # Allow admins to delete logs if needed
    
# Add Webhook model and admin
class WebhookEvent(models.Model):
    """Track webhook events"""
    EVENT_TYPES = [
        ('payment.succeeded', 'Payment Succeeded'),
        ('payment.failed', 'Payment Failed'),
        ('refund.succeeded', 'Refund Succeeded'),
        ('charge.dispute.created', 'Dispute Created'),
    ]
    
    event_id = models.CharField(max_length=100, unique=True)
    event_type = models.CharField(max_length=50, choices=EVENT_TYPES)
    gateway = models.CharField(max_length=50)
    payload = models.JSONField(default=dict)
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.gateway} - {self.event_type}"