from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import Order, OrderItem, OrderStatusHistory, ReturnRequest, Invoice

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    readonly_fields = ['product_name', 'product_sku', 'quantity', 'unit_price', 'total_price']
    extra = 0
    can_delete = False
    
    def has_add_permission(self, request, obj=None):
        return False

class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    readonly_fields = ['old_status', 'new_status', 'notes', 'created_by', 'created_at']
    extra = 0
    can_delete = False
    
    def has_add_permission(self, request, obj=None):
        return False

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        'order_number', 'user', 'status', 'payment_status', 
        'total_amount', 'created_at', 'admin_actions'
    ]
    list_filter = ['status', 'payment_status', 'created_at', 'payment_method']
    search_fields = ['order_number', 'user__username', 'user__email', 'transaction_id']
    readonly_fields = [
        'order_number', 'created_at', 'updated_at', 'paid_at', 
        'shipped_at', 'delivered_at'
    ]
    inlines = [OrderItemInline, OrderStatusHistoryInline]
    fieldsets = (
        ('Order Information', {
            'fields': ('order_number', 'user', 'status', 'payment_status')
        }),
        ('Pricing', {
            'fields': ('subtotal', 'shipping_cost', 'tax_amount', 'discount_amount', 'total_amount')
        }),
        ('Payment Information', {
            'fields': ('payment_method', 'payment_gateway', 'transaction_id')
        }),
        ('Shipping Information', {
            'fields': (
                'shipping_address', 'shipping_city', 'shipping_state',
                'shipping_country', 'shipping_zip_code', 'shipping_phone',
                'tracking_number', 'carrier'
            )
        }),
        ('Billing Information', {
            'fields': (
                'billing_address', 'billing_city', 'billing_state',
                'billing_country', 'billing_zip_code'
            )
        }),
        ('Dates', {
            'fields': ('created_at', 'updated_at', 'paid_at', 'shipped_at', 'delivered_at')
        }),
        ('Notes', {
            'fields': ('customer_notes', 'admin_notes')
        }),
    )
    
    def admin_actions(self, obj):
        return format_html(
            '<a href="{}" class="button">View</a> ',
            reverse('admin:orders_order_change', args=[obj.id])
        )
    admin_actions.short_description = 'Actions'

@admin.register(ReturnRequest)
class ReturnRequestAdmin(admin.ModelAdmin):
    list_display = ['id', 'order', 'user', 'reason', 'status', 'requested_at']
    list_filter = ['status', 'reason', 'requested_at']
    search_fields = ['order__order_number', 'user__username']
    readonly_fields = ['requested_at', 'resolved_at']
    list_editable = ['status']

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['invoice_number', 'order', 'created_at', 'pdf_link']
    search_fields = ['invoice_number', 'order__order_number']
    
    def pdf_link(self, obj):
        if obj.pdf_file:
            return format_html('<a href="{}" target="_blank">Download PDF</a>', obj.pdf_file.url)
        return "Not Generated"
    pdf_link.short_description = 'Invoice PDF'