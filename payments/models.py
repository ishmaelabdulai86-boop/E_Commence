# apps/payments/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid

class Payment(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ('card', 'Credit/Debit Card'),
        ('paypal', 'PayPal'),
        ('paystack', 'Paystack'),
        ('momo', 'Mobile Money'),
        ('bank_transfer', 'Bank Transfer'),
        ('cash', 'Cash on Delivery'),
    ]
    
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
    ]
    
    # Payment Information
    payment_id = models.CharField(max_length=50, unique=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    order = models.ForeignKey('orders.Order', on_delete=models.CASCADE, related_name='payments', null=True, blank=True)
    
    # Payment Details
    amount = models.DecimalField(max_digits=12, decimal_places=2)  # Increased from 10 to 12
    currency = models.CharField(max_length=3, default='USD')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    payment_gateway = models.CharField(max_length=50)  # stripe, paypal, paystack, etc.
    
    # Status
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    is_successful = models.BooleanField(default=False)
    
    # Gateway Response
    gateway_transaction_id = models.CharField(max_length=200, blank=True)  # Increased from 100
    gateway_response = models.JSONField(default=dict)  # Store full gateway response
    gateway_error = models.TextField(blank=True)
    
    # Customer Information
    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=20, blank=True)
    billing_address = models.TextField(blank=True)
    
    # Dates
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    metadata = models.JSONField(default=dict)  # Additional data
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['payment_id']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['user', 'created_at']),
        ]
    
    def __str__(self):
        return f"Payment {self.payment_id} - {self.amount} {self.currency}"
    
    def save(self, *args, **kwargs):
        if not self.payment_id:
            self.payment_id = f"PAY-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)
    
    def mark_as_paid(self, transaction_id=None):
        self.status = 'completed'
        self.is_successful = True
        self.paid_at = timezone.now()
        if transaction_id:
            self.gateway_transaction_id = transaction_id
        self.save()
    
    def mark_as_failed(self, error_message=None):
        self.status = 'failed'
        self.is_successful = False
        if error_message:
            self.gateway_error = error_message
        self.save()
    
    @property
    def is_refundable(self):
        return self.status == 'completed' and not self.is_refunded
    
    @property
    def is_refunded(self):
        return self.status == 'refunded'
    
    @property
    def formatted_amount(self):
        return f"{self.currency} {self.amount:.2f}"

class Refund(models.Model):
    REFUND_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    REFUND_REASON_CHOICES = [
        ('duplicate', 'Duplicate Transaction'),
        ('fraudulent', 'Fraudulent'),
        ('requested_by_customer', 'Requested by Customer'),
        ('product_return', 'Product Return'),
        ('other', 'Other'),
    ]
    
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='refunds')
    order = models.ForeignKey('orders.Order', on_delete=models.CASCADE, related_name='refunds', null=True, blank=True)
    
    # Refund Details
    refund_id = models.CharField(max_length=50, unique=True, default=uuid.uuid4)
    amount = models.DecimalField(max_digits=12, decimal_places=2)  # Increased from 10
    currency = models.CharField(max_length=3, default='USD')
    reason = models.CharField(max_length=50, choices=REFUND_REASON_CHOICES)
    description = models.TextField(blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=REFUND_STATUS_CHOICES, default='pending')
    is_completed = models.BooleanField(default=False)
    
    # Gateway Response
    gateway_refund_id = models.CharField(max_length=200, blank=True)  # Increased from 100
    gateway_response = models.JSONField(default=dict)
    gateway_error = models.TextField(blank=True)
    
    # Request Information
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-requested_at']
        indexes = [
            models.Index(fields=['refund_id']),
            models.Index(fields=['status']),
            models.Index(fields=['requested_at']),
        ]
    
    def __str__(self):
        return f"Refund {self.refund_id} - {self.amount} {self.currency}"
    
    def save(self, *args, **kwargs):
        if not self.refund_id:
            self.refund_id = f"REF-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)
    
    def mark_as_completed(self, gateway_refund_id=None):
        self.status = 'completed'
        self.is_completed = True
        self.processed_at = timezone.now()
        if gateway_refund_id:
            self.gateway_refund_id = gateway_refund_id
        self.save()

class PaymentGatewayConfig(models.Model):
    """Configuration for different payment gateways"""
    GATEWAY_CHOICES = [
        ('stripe', 'Stripe'),
        ('paypal', 'PayPal'),
        ('paystack', 'Paystack'),
        ('flutterwave', 'Flutterwave'),
        ('momo', 'Mobile Money'),
    ]
    
    name = models.CharField(max_length=50, choices=GATEWAY_CHOICES)
    display_name = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    is_test_mode = models.BooleanField(default=True)
    
    # API Credentials
    api_key = models.CharField(max_length=500, blank=True)  # Increased from 255
    secret_key = models.CharField(max_length=500, blank=True)
    webhook_secret = models.CharField(max_length=500, blank=True)
    
    # Configuration
    supported_currencies = models.JSONField(default=list)  # List of supported currencies
    supported_countries = models.JSONField(default=list)  # List of supported countries
    payment_methods = models.JSONField(default=list)  # Supported payment methods
    
    # Fees
    transaction_fee_percent = models.DecimalField(max_digits=5, decimal_places=2, default=2.9)
    transaction_fee_fixed = models.DecimalField(max_digits=10, decimal_places=2, default=0.30)
    
    # Metadata
    config_data = models.JSONField(default=dict)  # Additional gateway-specific config
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Payment Gateway Configuration'
        verbose_name_plural = 'Payment Gateway Configurations'
        constraints = [
            models.UniqueConstraint(fields=['name'], name='unique_payment_gateway')
        ]
    
    def __str__(self):
        return f"{self.display_name or self.get_name_display()} ({'Live' if not self.is_test_mode else 'Test'})"
    
    def save(self, *args, **kwargs):
        if not self.display_name:
            self.display_name = self.get_name_display()
        super().save(*args, **kwargs)
    
    def calculate_fee(self, amount):
        """Calculate gateway fee for a given amount"""
        fee = (amount * self.transaction_fee_percent / 100) + self.transaction_fee_fixed
        return round(fee, 2)
    
    @property
    def is_configured(self):
        """Check if gateway has required API credentials"""
        if self.name in ['stripe', 'paystack', 'flutterwave']:
            return bool(self.secret_key)
        elif self.name == 'paypal':
            return bool(self.api_key and self.secret_key)
        return True

class TransactionLog(models.Model):
    """Log all payment gateway transactions"""
    gateway = models.CharField(max_length=50)
    transaction_type = models.CharField(max_length=50)  # payment, refund, webhook, etc.
    
    # Request/Response Data
    request_data = models.JSONField(default=dict)
    response_data = models.JSONField(default=dict)
    headers = models.JSONField(default=dict)
    
    # Status
    is_successful = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)
    
    # Timing
    duration_ms = models.IntegerField(default=0)  # Request duration in milliseconds
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['gateway', 'created_at']),
            models.Index(fields=['transaction_type', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.gateway} - {self.transaction_type} - {self.created_at}"
    
class PaymentReconciliation(models.Model):
    """Track payment reconciliation"""
    reconciliation_id = models.CharField(max_length=50, unique=True)
    gateway = models.CharField(max_length=50)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    
    # Reconciliation results
    total_transactions = models.IntegerField(default=0)
    matched_transactions = models.IntegerField(default=0)
    unmatched_transactions = models.IntegerField(default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discrepancy_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Status
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ], default='pending')
    
    # Results
    results = models.JSONField(default=dict)
    error_message = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    def reconcile(self):
        """Perform reconciliation"""
        try:
            # Fetch transactions from gateway
            gateway_transactions = self.fetch_gateway_transactions()
            
            # Get local transactions
            local_transactions = Payment.objects.filter(
                payment_gateway=self.gateway,
                created_at__range=(self.start_date, self.end_date)
            )
            
            # Match transactions
            matches, unmatched = self.match_transactions(
                gateway_transactions, 
                local_transactions
            )
            
            # Update reconciliation results
            self.total_transactions = len(gateway_transactions)
            self.matched_transactions = len(matches)
            self.unmatched_transactions = len(unmatched)
            self.results = {
                'matches': matches,
                'unmatched': unmatched,
            }
            self.status = 'completed'
            self.completed_at = timezone.now()
            
        except Exception as e:
            self.status = 'failed'
            self.error_message = str(e)
        
        self.save()