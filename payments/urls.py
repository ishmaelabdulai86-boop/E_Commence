# apps/payments/urls.py
from django.urls import path
from . import views

app_name = 'payments'  # Add this for namespace

urlpatterns = [
    # Payment Processing
    path('process/<int:order_id>/', views.payment_process, name='payment_process'),
    path('process/', views.payment_process, name='payment_process'),
    path('success/<str:payment_id>/', views.payment_success, name='payment_success'),
    path('failed/<str:payment_id>/', views.payment_failed, name='payment_failed'),
    path('detail/<str:payment_id>/', views.payment_detail, name='payment_detail'),
    
    # Webhooks
    path('webhook/stripe/', views.stripe_webhook, name='stripe_webhook'),
    path('webhook/paystack/', views.paystack_webhook, name='paystack_webhook'),
    
    # Refunds
    path('refund/<str:payment_id>/', views.create_refund, name='create_refund'),
    
    # History & Methods
    path('history/', views.payment_history, name='payment_history'),
    path('methods/', views.payment_methods, name='payment_methods'),
    path('verify/<str:payment_id>/', views.verify_payment, name='verify_payment'),
    
    # Callbacks
    path('paystack/callback/', views.paystack_webhook, name='paystack_callback'),
    path('paypal/success/', views.payment_success, name='paypal_success'),
    path('paypal/cancel/', views.payment_failed, name='paypal_cancel'),
    
    # Admin routes - specific paths must come BEFORE dynamic paths
    path('admin/payments/dashboard/', views.admin_payment_dashboard, name='admin_payment_dashboard'),
    path('admin/payments/export/', views.export_payments_csv, name='export_payments_csv'),
    path('admin/payments/', views.admin_payment_list, name='admin_payment_list'),
    path('admin/payments/<str:payment_id>/refund/', views.admin_payment_refund, name='admin_payment_refund'),
    path('admin/payments/<str:payment_id>/', views.admin_payment_detail, name='admin_payment_detail'),
    path('admin/refunds/', views.admin_refund_list, name='admin_refund_list'),
    path('admin/refunds/<int:refund_id>/update-status/', views.admin_update_refund_status, name='admin_update_refund_status'),
    path('admin/refunds/<int:refund_id>/', views.admin_refund_detail, name='admin_refund_detail'),
    path('admin/transaction-logs/', views.admin_transaction_logs, name='admin_transaction_logs'),
    path('admin/gateways/', views.admin_gateway_list, name='admin_gateway_list'),
    path('admin/gateways/<int:gateway_id>/edit/', views.admin_gateway_edit, name='admin_gateway_edit'),
    path('admin/gateways/<int:gateway_id>/', views.admin_gateway_detail, name='admin_gateway_detail'),
]