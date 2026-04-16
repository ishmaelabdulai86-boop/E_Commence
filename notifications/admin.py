from django.contrib import admin

# Register your models here.
from django.contrib import admin
from django.utils.html import format_html
from .models import (
    NotificationTemplate, Notification, NotificationPreference,
    EmailLog, SMSLog, PushNotificationDevice
)
from django.urls import reverse

@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'template_type', 'category', 'is_active', 'priority', 'updated_at', 'custom_actions']
    list_filter = ['template_type', 'category', 'is_active']
    search_fields = ['name', 'subject']
    list_editable = ['is_active', 'priority']
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'template_type', 'category', 'is_active', 'priority')
        }),
        ('Content', {
            'fields': ('subject', 'html_content', 'text_content', 'push_content')
        }),
        ('Variables', {
            'fields': ('available_variables',),
            'classes': ('collapse',),
        }),
    )
    def custom_actions(self, obj):
        return format_html(
            '<a href="{}" class="btn btn-sm btn-outline-primary">Edit</a>',
            reverse('admin_template_detail', args=[obj.id])
        )
    custom_actions.short_description = 'Actions'

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['notification_id', 'user', 'notification_type', 'title', 'status', 'created_at', 'admin_actions']
    list_filter = ['notification_type', 'status', 'created_at']
    search_fields = ['user__username', 'title', 'message']
    readonly_fields = ['created_at', 'sent_at', 'delivered_at', 'read_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('notification_id', 'user', 'notification_type', 'template')
        }),
        ('Content', {
            'fields': ('title', 'message', 'data')
        }),
        ('Status', {
            'fields': ('status', 'is_read')
        }),
        ('Delivery Times', {
            'fields': ('sent_at', 'delivered_at', 'read_at'),
            'classes': ('collapse',),
        }),
        ('Response', {
            'fields': ('provider_response', 'error_message', 'retry_count'),
            'classes': ('collapse',),
        }),
        ('Metadata', {
            'fields': ('metadata',),
            'classes': ('collapse',),
        }),
    )
    
    def admin_actions(self, obj):
        return format_html(
            '<a href="{}" class="btn btn-sm btn-outline-primary">View</a>',
            reverse('admin_notification_detail', args=[obj.notification_id])
        )
    admin_actions.short_description = 'Actions'

@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ['user', 'do_not_disturb', 'updated_at']
    list_filter = ['do_not_disturb']
    search_fields = ['user__username', 'user__email']
    
    fieldsets = (
        ('Email Preferences', {
            'fields': (
                'email_order_updates', 'email_payment_updates',
                'email_shipping_updates', 'email_promotions', 'email_account_updates'
            )
        }),
        ('SMS Preferences', {
            'fields': (
                'sms_order_updates', 'sms_payment_updates',
                'sms_shipping_updates', 'sms_promotions'
            )
        }),
        ('Push Notification Preferences', {
            'fields': (
                'push_order_updates', 'push_payment_updates',
                'push_shipping_updates', 'push_promotions'
            )
        }),
        ('WhatsApp Preferences', {
            'fields': (
                'whatsapp_order_updates', 'whatsapp_payment_updates',
                'whatsapp_shipping_updates', 'whatsapp_promotions'
            )
        }),
        ('Global Settings', {
            'fields': ('do_not_disturb', 'quiet_hours_start', 'quiet_hours_end')
        }),
    )

@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ['to_email', 'subject', 'status', 'sent_at', 'created_at']
    list_filter = ['status', 'provider', 'created_at']
    search_fields = ['to_email', 'subject']
    readonly_fields = ['created_at', 'sent_at']
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False

@admin.register(SMSLog)
class SMSLogAdmin(admin.ModelAdmin):
    list_display = ['to_phone', 'message_preview', 'status', 'sent_at', 'created_at']
    list_filter = ['status', 'provider', 'created_at']
    search_fields = ['to_phone', 'message']
    readonly_fields = ['created_at', 'sent_at']
    
    def message_preview(self, obj):
        return obj.message[:50] + '...' if len(obj.message) > 50 else obj.message
    message_preview.short_description = 'Message'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False

@admin.register(PushNotificationDevice)
class PushNotificationDeviceAdmin(admin.ModelAdmin):
    list_display = ['user', 'platform', 'device_model', 'is_active', 'last_seen']
    list_filter = ['platform', 'is_active', 'last_seen']
    search_fields = ['user__username', 'device_token']
    readonly_fields = ['last_seen', 'created_at']

