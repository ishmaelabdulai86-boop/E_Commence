from django.db import models

# Create your models here.
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.html import strip_tags
import uuid

class NotificationTemplate(models.Model):
    """Templates for different types of notifications"""
    TEMPLATE_TYPE_CHOICES = [
        ('email', 'Email'),
        ('sms', 'SMS'),
        ('push', 'Push Notification'),
        ('whatsapp', 'WhatsApp'),
    ]
    
    NOTIFICATION_CATEGORY_CHOICES = [
        ('order', 'Order'),
        ('payment', 'Payment'),
        ('shipping', 'Shipping'),
        ('account', 'Account'),
        ('promotional', 'Promotional'),
        ('system', 'System'),
    ]
    
    name = models.CharField(max_length=100)
    template_type = models.CharField(max_length=20, choices=TEMPLATE_TYPE_CHOICES)
    category = models.CharField(max_length=20, choices=NOTIFICATION_CATEGORY_CHOICES)
    subject = models.CharField(max_length=200, blank=True)
    
    # Template content
    html_content = models.TextField(blank=True)  # For email/rich notifications
    text_content = models.TextField(blank=True)  # For SMS/plain text
    push_content = models.TextField(blank=True)  # For push notifications
    
    # Variables available in template
    available_variables = models.JSONField(default=list)
    
    # Configuration
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(default=1)  # 1=Low, 2=Medium, 3=High, 4=Urgent
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['category', 'priority', 'name']
        unique_together = ['name', 'template_type']
    
    def __str__(self):
        return f"{self.name} ({self.get_template_type_display()})"
    
    def render(self, context):
        """Render template with context variables"""
        from django.template import Template, Context
        
        template = Template(self.html_content)
        return template.render(Context(context))

class Notification(models.Model):
    """Individual notifications sent to users"""
    NOTIFICATION_TYPE_CHOICES = [
        ('email', 'Email'),
        ('sms', 'SMS'),
        ('push', 'Push Notification'),
        ('in_app', 'In-App Notification'),
        ('whatsapp', 'WhatsApp'),
    ]
    
    NOTIFICATION_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    # Identification
    notification_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    
    # Content
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPE_CHOICES)
    template = models.ForeignKey(NotificationTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    
    title = models.CharField(max_length=200)
    message = models.TextField()
    data = models.JSONField(default=dict)  # Additional data for the notification
    
    # Status
    status = models.CharField(max_length=20, choices=NOTIFICATION_STATUS_CHOICES, default='pending')
    is_read = models.BooleanField(default=False)
    
    # Delivery
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    
    # Response/Error
    provider_response = models.JSONField(default=dict)
    error_message = models.TextField(blank=True)
    retry_count = models.IntegerField(default=0)
    
    # Metadata
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['notification_type', 'status']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.get_notification_type_display()} to {self.user.username}: {self.title}"
    
    def mark_as_sent(self):
        self.status = 'sent'
        self.sent_at = timezone.now()
        self.save()
    
    def mark_as_delivered(self):
        self.status = 'delivered'
        self.delivered_at = timezone.now()
        self.save()
    
    def mark_as_read(self):
        self.status = 'read'
        self.is_read = True
        self.read_at = timezone.now()
        self.save()
    
    def mark_as_failed(self, error_message):
        self.status = 'failed'
        self.error_message = error_message
        self.save()

class NotificationPreference(models.Model):
    """User preferences for notifications"""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notification_preferences')
    
    # Email preferences
    email_order_updates = models.BooleanField(default=True)
    email_payment_updates = models.BooleanField(default=True)
    email_shipping_updates = models.BooleanField(default=True)
    email_promotions = models.BooleanField(default=True)
    email_account_updates = models.BooleanField(default=True)
    
    # SMS preferences
    sms_order_updates = models.BooleanField(default=False)
    sms_payment_updates = models.BooleanField(default=True)  # Important for OTP
    sms_shipping_updates = models.BooleanField(default=False)
    sms_promotions = models.BooleanField(default=False)
    
    # Push notification preferences
    push_order_updates = models.BooleanField(default=True)
    push_payment_updates = models.BooleanField(default=True)
    push_shipping_updates = models.BooleanField(default=True)
    push_promotions = models.BooleanField(default=False)
    
    # WhatsApp preferences
    whatsapp_order_updates = models.BooleanField(default=False)
    whatsapp_payment_updates = models.BooleanField(default=False)
    whatsapp_shipping_updates = models.BooleanField(default=False)
    whatsapp_promotions = models.BooleanField(default=False)
    
    # Global settings
    do_not_disturb = models.BooleanField(default=False)
    quiet_hours_start = models.TimeField(null=True, blank=True)  # 22:00
    quiet_hours_end = models.TimeField(null=True, blank=True)    # 08:00
    
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Notification Preference'
        verbose_name_plural = 'Notification Preferences'
    
    def __str__(self):
        return f"Notification preferences for {self.user.username}"
    
    def can_send_notification(self, category, notification_type):
        """Check if user allows this type of notification"""
        
        if self.do_not_disturb:
            # Check if current time is within quiet hours
            now = timezone.now().time()
            if self.quiet_hours_start and self.quiet_hours_end:
                if self.quiet_hours_start <= self.quiet_hours_end:
                    if self.quiet_hours_start <= now <= self.quiet_hours_end:
                        return False
                else:
                    # Crossing midnight
                    if now >= self.quiet_hours_start or now <= self.quiet_hours_end:
                        return False
        
        # Map category and type to preference field
        preference_map = {
            ('order', 'email'): 'email_order_updates',
            ('payment', 'email'): 'email_payment_updates',
            ('shipping', 'email'): 'email_shipping_updates',
            ('promotional', 'email'): 'email_promotions',
            ('account', 'email'): 'email_account_updates',
            
            ('order', 'sms'): 'sms_order_updates',
            ('payment', 'sms'): 'sms_payment_updates',
            ('shipping', 'sms'): 'sms_shipping_updates',
            ('promotional', 'sms'): 'sms_promotions',
            
            ('order', 'push'): 'push_order_updates',
            ('payment', 'push'): 'push_payment_updates',
            ('shipping', 'push'): 'push_shipping_updates',
            ('promotional', 'push'): 'push_promotions',
            
            ('order', 'whatsapp'): 'whatsapp_order_updates',
            ('payment', 'whatsapp'): 'whatsapp_payment_updates',
            ('shipping', 'whatsapp'): 'whatsapp_shipping_updates',
            ('promotional', 'whatsapp'): 'whatsapp_promotions',
        }
        
        preference_field = preference_map.get((category, notification_type))
        if preference_field:
            return getattr(self, preference_field, False)
        
        return True  # Default allow if not specified

class EmailLog(models.Model):
    """Log of all emails sent"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('bounced', 'Bounced'),
        ('complained', 'Complained'),
        ('failed', 'Failed'),
    ]
    
    # Recipient
    to_email = models.EmailField()
    to_name = models.CharField(max_length=100, blank=True)
    
    # Content
    subject = models.CharField(max_length=200)
    html_content = models.TextField()
    text_content = models.TextField(blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    sent_at = models.DateTimeField(null=True, blank=True)
    
    # Provider Response
    provider = models.CharField(max_length=50, default='smtp')
    provider_message_id = models.CharField(max_length=200, blank=True)
    provider_response = models.JSONField(default=dict)
    
    # Metadata
    template = models.ForeignKey(NotificationTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['to_email', 'created_at']),
            models.Index(fields=['status', 'created_at']),
        ]
    
    def __str__(self):
        return f"Email to {self.to_email}: {self.subject}"

class SMSLog(models.Model):
    """Log of all SMS sent"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed'),
    ]
    
    # Recipient
    to_phone = models.CharField(max_length=20)
    to_name = models.CharField(max_length=100, blank=True)
    
    # Content
    message = models.TextField()
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    sent_at = models.DateTimeField(null=True, blank=True)
    
    # Provider Response
    provider = models.CharField(max_length=50, default='twilio')
    provider_message_id = models.CharField(max_length=200, blank=True)
    provider_response = models.JSONField(default=dict)
    
    # Metadata
    template = models.ForeignKey(NotificationTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'SMS Log'
        verbose_name_plural = 'SMS Logs'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"SMS to {self.to_phone}: {self.message[:50]}..."

class PushNotificationDevice(models.Model):
    """Registered devices for push notifications"""
    PLATFORM_CHOICES = [
        ('ios', 'iOS'),
        ('android', 'Android'),
        ('web', 'Web'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='push_devices')
    device_token = models.CharField(max_length=255, unique=True)
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    
    # Device Information
    device_model = models.CharField(max_length=100, blank=True)
    os_version = models.CharField(max_length=50, blank=True)
    app_version = models.CharField(max_length=50, blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    last_seen = models.DateTimeField(auto_now=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-last_seen']
        indexes = [
            models.Index(fields=['user', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.get_platform_display()} device for {self.user.username}"