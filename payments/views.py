# apps/payments/views.py
import json
import stripe
import time
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET, require_http_methods
from django.conf import settings
from django.utils import timezone
from django.urls import reverse
from django.db import transaction
from datetime import datetime
from .models import Payment, Refund, PaymentGatewayConfig, TransactionLog
from orders.models import Order
from cart.models import Cart

# Initialize payment gateways
stripe.api_key = getattr(settings, 'STRIPE_SECRET_KEY', '')
# Note: paystackapi import might need to be installed separately

@login_required
def payment_process(request, order_id=None):
    """Process payment for an order"""
    
    if order_id:
        order = get_object_or_404(Order, id=order_id, user=request.user)
    else:
        # Get latest pending order for user
        order = Order.objects.filter(
            user=request.user,
            payment_status='pending'
        ).order_by('-created_at').first()
    
    if not order:
        messages.error(request, 'No pending order found.')
        return redirect('cart')
    
    # Check if order already has successful payment
    if order.payments.filter(is_successful=True).exists():
        messages.info(request, 'This order has already been paid.')
        return redirect('order_detail', order_number=order.order_number)
    
    # Get payment method from request
    payment_method = request.POST.get('payment_method', 'card')
    
    try:
        if payment_method == 'card':
            return process_stripe_payment(request, order)
        elif payment_method == 'paypal':
            return process_paypal_payment(request, order)
        elif payment_method == 'paystack':
            return process_paystack_payment(request, order)
        elif payment_method == 'momo':
            return process_momo_payment(request, order)
        elif payment_method == 'cash':
            return process_cash_payment(request, order)
        else:
            messages.error(request, 'Invalid payment method selected.')
            return redirect('checkout')
    
    except Exception as e:
        messages.error(request, f'Payment processing error: {str(e)}')
        return redirect('checkout')

def process_stripe_payment(request, order):
    """Process payment via Stripe"""
    
    if not hasattr(settings, 'STRIPE_SECRET_KEY') or not settings.STRIPE_SECRET_KEY:
        messages.error(request, 'Stripe payment is not configured.')
        return redirect('checkout')
    
    try:
        start_time = time.time()
        
        # Create Stripe customer if not exists
        customer = stripe.Customer.create(
            email=request.user.email,
            name=request.user.get_full_name() or request.user.username,
            metadata={
                'user_id': request.user.id,
                'order_id': order.id,
            }
        )
        
        # Create Stripe payment intent
        intent = stripe.PaymentIntent.create(
            amount=int(order.total_amount * 100),  # Convert to cents
            currency='usd',
            customer=customer.id,
            metadata={
                'order_number': order.order_number,
                'user_id': request.user.id,
            },
            description=f"Payment for order {order.order_number}",
        )
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        # Create payment record
        payment = Payment.objects.create(
            user=request.user,
            order=order,
            amount=order.total_amount,
            currency='USD',
            payment_method='card',
            payment_gateway='stripe',
            customer_email=request.user.email,
            gateway_response={'intent_id': intent.id},
            metadata={
                'stripe_customer_id': customer.id,
                'stripe_intent_id': intent.id,
            }
        )
        
        # Log transaction
        TransactionLog.objects.create(
            gateway='stripe',
            transaction_type='payment_intent_create',
            request_data={'order_id': order.id, 'amount': order.total_amount},
            response_data=intent,
            is_successful=True,
            duration_ms=duration_ms,
        )
        
        context = {
            'order': order,
            'payment': payment,
            'stripe_public_key': getattr(settings, 'STRIPE_PUBLIC_KEY', ''),
            'client_secret': intent.client_secret,
            'payment_intent_id': intent.id,
        }
        
        return render(request, 'payments/stripe.html', context)
    
    except stripe.error.StripeError as e:
        duration_ms = int((time.time() - start_time) * 1000) if 'start_time' in locals() else 0
        
        # Log error
        TransactionLog.objects.create(
            gateway='stripe',
            transaction_type='payment_intent_create',
            request_data={'order_id': order.id, 'amount': order.total_amount},
            response_data={'error': str(e)},
            is_successful=False,
            error_message=str(e),
            duration_ms=duration_ms,
        )
        
        messages.error(request, f'Stripe error: {str(e)}')
        return redirect('checkout')

def process_paystack_payment(request, order):
    """Process payment via Paystack (Africa-focused)"""
    
    if not hasattr(settings, 'PAYSTACK_SECRET_KEY') or not settings.PAYSTACK_SECRET_KEY:
        messages.error(request, 'Paystack payment is not configured.')
        return redirect('checkout')
    
    try:
        # Note: In production, use the official Paystack Python SDK
        import requests
        
        headers = {
            'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}',
            'Content-Type': 'application/json',
        }
        
        payload = {
            'email': request.user.email,
            'amount': int(order.total_amount * 100),  # Convert to kobo
            'reference': f"ORDER_{order.order_number}_{int(time.time())}",
            'callback_url': request.build_absolute_uri(reverse('paystack_callback')),
            'metadata': {
                'order_id': order.id,
                'user_id': request.user.id,
                'order_number': order.order_number,
            }
        }
        
        response = requests.post(
            'https://api.paystack.co/transaction/initialize',
            headers=headers,
            json=payload
        )
        
        response_data = response.json()
        
        if response_data.get('status'):
            # Create payment record
            payment = Payment.objects.create(
                user=request.user,
                order=order,
                amount=order.total_amount,
                currency='NGN',
                payment_method='paystack',
                payment_gateway='paystack',
                customer_email=request.user.email,
                gateway_transaction_id=response_data['data']['reference'],
                gateway_response=response_data,
                metadata={
                    'paystack_reference': response_data['data']['reference'],
                    'authorization_url': response_data['data']['authorization_url'],
                }
            )
            
            # Log transaction
            TransactionLog.objects.create(
                gateway='paystack',
                transaction_type='transaction_initialize',
                request_data=payload,
                response_data=response_data,
                is_successful=True,
                duration_ms=response.elapsed.microseconds // 1000,
            )
            
            # Redirect to Paystack payment page
            return redirect(response_data['data']['authorization_url'])
        else:
            raise Exception(response_data.get('message', 'Paystack initialization failed'))
    
    except Exception as e:
        # Log error
        TransactionLog.objects.create(
            gateway='paystack',
            transaction_type='transaction_initialize',
            request_data={'order_id': order.id, 'amount': order.total_amount},
            response_data={'error': str(e)},
            is_successful=False,
            error_message=str(e),
        )
        
        messages.error(request, f'Paystack error: {str(e)}')
        return redirect('checkout')

def process_paypal_payment(request, order):
    """Process payment via PayPal"""
    
    try:
        # Create PayPal order ID
        paypal_order_id = f"PAYPAL_{order.order_number}_{int(time.time())}"
        
        # Create payment record
        payment = Payment.objects.create(
            user=request.user,
            order=order,
            amount=order.total_amount,
            currency='USD',
            payment_method='paypal',
            payment_gateway='paypal',
            customer_email=request.user.email,
            gateway_transaction_id=paypal_order_id,
            metadata={
                'paypal_order_id': paypal_order_id,
                'return_url': request.build_absolute_uri(reverse('payment_success', args=[payment.payment_id])),
                'cancel_url': request.build_absolute_uri(reverse('payment_failed', args=[payment.payment_id])),
            }
        )
        
        # Log transaction
        TransactionLog.objects.create(
            gateway='paypal',
            transaction_type='order_create',
            request_data={'order_id': order.id, 'amount': order.total_amount},
            response_data={'order_id': paypal_order_id},
            is_successful=True,
        )
        
        # In production, you would integrate with PayPal API
        # For now, show a manual payment confirmation page
        context = {
            'order': order,
            'payment': payment,
            'paypal_order_id': paypal_order_id,
        }
        
        return render(request, 'payments/paypal.html', context)
    
    except Exception as e:
        # Log error
        TransactionLog.objects.create(
            gateway='paypal',
            transaction_type='order_create',
            request_data={'order_id': order.id, 'amount': order.total_amount},
            response_data={'error': str(e)},
            is_successful=False,
            error_message=str(e),
        )
        
        messages.error(request, f'PayPal error: {str(e)}')
        return redirect('orders:checkout')

def process_momo_payment(request, order):
    """Process payment via Mobile Money (Africa)"""
    
    try:
        # Get mobile money provider
        momo_provider = request.POST.get('momo_provider', 'mtn')
        phone_number = request.POST.get('momo_number')
        
        if not phone_number:
            messages.error(request, 'Phone number is required for Mobile Money payment.')
            return redirect('checkout')
        
        # Validate phone number
        if not phone_number.replace('+', '').isdigit():
            messages.error(request, 'Invalid phone number format.')
            return redirect('checkout')
        
        # Determine currency based on provider
        currency_map = {
            'mtn': 'GHS',  # Ghana
            'vodafone': 'GHS',
            'airtel': 'KES',  # Kenya
            'orange': 'XOF',  # West Africa
        }
        
        currency = currency_map.get(momo_provider, 'USD')
        
        # Create payment record
        payment = Payment.objects.create(
            user=request.user,
            order=order,
            amount=order.total_amount,
            currency=currency,
            payment_method='momo',
            payment_gateway=momo_provider,
            customer_email=request.user.email,
            customer_phone=phone_number,
            metadata={
                'momo_provider': momo_provider,
                'phone_number': phone_number,
                'network': get_momo_network(momo_provider),
            }
        )
        
        # Log transaction
        TransactionLog.objects.create(
            gateway='momo',
            transaction_type='payment_initiate',
            request_data={
                'order_id': order.id,
                'amount': order.total_amount,
                'provider': momo_provider,
                'phone': phone_number,
            },
            response_data={'status': 'pending'},
            is_successful=True,
        )
        
        context = {
            'order': order,
            'payment': payment,
            'provider': momo_provider,
            'phone_number': phone_number,
            'currency': currency,
        }
        
        return render(request, 'payments/momo.html', context)
    
    except Exception as e:
        # Log error
        TransactionLog.objects.create(
            gateway='momo',
            transaction_type='payment_initiate',
            request_data={'order_id': order.id, 'amount': order.total_amount},
            response_data={'error': str(e)},
            is_successful=False,
            error_message=str(e),
        )
        
        messages.error(request, f'Mobile Money error: {str(e)}')
        return redirect('checkout')

def process_cash_payment(request, order):
    """Process cash on delivery payment"""
    
    try:
        # Create payment record for cash payment
        payment = Payment.objects.create(
            user=request.user,
            order=order,
            amount=order.total_amount,
            currency='USD',
            payment_method='cash',
            payment_gateway='cash',
            customer_email=request.user.email,
            status='completed',  # Cash payments are automatically completed
            is_successful=True,
            paid_at=timezone.now(),
            metadata={
                'payment_type': 'cash_on_delivery',
                'instructions': 'Payment to be collected on delivery',
            }
        )
        
        # Update order status
        order.payment_status = 'pending'  # Still pending until cash is collected
        order.status = 'confirmed'
        order.save()
        
        # Log transaction
        TransactionLog.objects.create(
            gateway='cash',
            transaction_type='cash_payment',
            request_data={'order_id': order.id, 'amount': order.total_amount},
            response_data={'status': 'created'},
            is_successful=True,
        )
        
        messages.success(request, 'Cash on delivery order confirmed! You will pay when your order arrives.')
        return redirect('payments:payment_success', payment_id=payment.payment_id)
    
    except Exception as e:
        messages.error(request, f'Error processing cash payment: {str(e)}')
        return redirect('checkout')

def get_momo_network(provider):
    """Get mobile money network name"""
    networks = {
        'mtn': 'MTN Mobile Money',
        'vodafone': 'Vodafone Cash',
        'airtel': 'Airtel Money',
        'orange': 'Orange Money',
        'tigo': 'Tigo Cash',
    }
    return networks.get(provider, 'Mobile Money')

# Add these functions to your payments/views.py

def handle_charge_refunded(charge):
    """Handle Stripe charge refunded webhook"""
    with transaction.atomic():
        try:
            # Find payment by charge ID
            payment = Payment.objects.filter(
                gateway_transaction_id=charge['id']
            ).first()
            
            if not payment:
                # Try to find by payment intent
                payment_intent_id = charge.get('payment_intent')
                if payment_intent_id:
                    payment = Payment.objects.filter(
                        metadata__stripe_intent_id=payment_intent_id
                    ).first()
            
            if payment:
                # Find or create refund
                refund, created = Refund.objects.get_or_create(
                    payment=payment,
                    gateway_refund_id=charge.get('id'),
                    defaults={
                        'amount': Decimal(charge['amount_refunded']) / 100,
                        'currency': charge['currency'],
                        'reason': 'requested_by_customer',
                        'status': 'completed',
                        'is_completed': True,
                        'processed_at': timezone.now(),
                        'gateway_response': charge,
                    }
                )
                
                if not created:
                    refund.amount = Decimal(charge['amount_refunded']) / 100
                    refund.status = 'completed'
                    refund.is_completed = True
                    refund.processed_at = timezone.now()
                    refund.gateway_response = charge
                    refund.save()
                
                # Update payment status
                if charge['refunded']:
                    payment.status = 'refunded'
                elif charge['amount_refunded'] > 0:
                    payment.status = 'partially_refunded'
                payment.save()
                
                # Update order status if exists
                if payment.order:
                    payment.order.status = 'refunded'
                    payment.order.save()
        
        except Exception as e:
            raise e

def handle_payment_intent_cancelled(payment_intent):
    """Handle Stripe payment intent cancelled webhook"""
    try:
        payment = Payment.objects.filter(
            metadata__stripe_intent_id=payment_intent['id']
        ).first()
        
        if payment:
            payment.status = 'cancelled'
            payment.gateway_response = payment_intent
            payment.save()
    
    except Exception as e:
        raise e

def handle_paystack_charge_failed(data):
    """Handle failed Paystack charge"""
    try:
        reference = data.get('reference')
        payment = Payment.objects.filter(
            gateway_transaction_id=reference
        ).first()
        
        if payment:
            error_message = data.get('message', 'Payment failed')
            payment.mark_as_failed(error_message)
            payment.gateway_response = data
            payment.save()
    
    except Exception as e:
        raise e

def handle_paystack_refund_processed(data):
    """Handle Paystack refund processed webhook"""
    try:
        refund_id = data.get('id')
        reference = data.get('reference')
        
        # Try to find refund by gateway refund ID or reference
        refund = Refund.objects.filter(
            gateway_refund_id=refund_id
        ).first()
        
        if not refund and reference:
            refund = Refund.objects.filter(
                gateway_refund_id=reference
            ).first()
        
        if refund:
            if data.get('status') == 'success':
                refund.mark_as_completed(refund_id)
                refund.gateway_response = data
                refund.save()
                
                # Update payment status
                payment = refund.payment
                total_refunded = payment.refunds.filter(status='completed').aggregate(
                    total=Sum('amount')
                )['total'] or Decimal('0')
                
                if total_refunded >= payment.amount:
                    payment.status = 'refunded'
                else:
                    payment.status = 'partially_refunded'
                payment.save()
                
                # Update order status
                if refund.order:
                    refund.order.status = 'refunded'
                    refund.order.save()
            else:
                refund.status = 'failed'
                refund.gateway_error = data.get('message', 'Refund failed')
                refund.save()
    
    except Exception as e:
        raise e

def process_paystack_refund(refund):
    """Process refund via Paystack"""
    try:
        import requests
        
        if not hasattr(settings, 'PAYSTACK_SECRET_KEY') or not settings.PAYSTACK_SECRET_KEY:
            refund.status = 'failed'
            refund.gateway_error = 'Paystack not configured'
            refund.save()
            return
        
        headers = {
            'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}',
            'Content-Type': 'application/json',
        }
        
        # Paystack expects amount in kobo (for NGN)
        amount_in_kobo = int(refund.amount * 100)
        
        payload = {
            'transaction': refund.payment.gateway_transaction_id,
            'amount': amount_in_kobo,
            'currency': refund.currency.lower(),
            'customer_note': refund.description or f"Refund for order {refund.order.order_number if refund.order else 'N/A'}",
        }
        
        response = requests.post(
            'https://api.paystack.co/refund',
            headers=headers,
            json=payload
        )
        
        response_data = response.json()
        
        if response_data.get('status'):
            refund.gateway_refund_id = response_data['data']['id']
            refund.status = 'processing'  # Paystack refunds are async
            refund.gateway_response = response_data
            refund.save()
            
            # Log transaction
            TransactionLog.objects.create(
                gateway='paystack',
                transaction_type='refund',
                request_data=payload,
                response_data=response_data,
                is_successful=True,
                duration_ms=response.elapsed.microseconds // 1000,
            )
        else:
            refund.status = 'failed'
            refund.gateway_error = response_data.get('message', 'Refund failed')
            refund.gateway_response = response_data
            refund.save()
            
            # Log error
            TransactionLog.objects.create(
                gateway='paystack',
                transaction_type='refund',
                request_data=payload,
                response_data=response_data,
                is_successful=False,
                error_message=refund.gateway_error,
            )
    
    except Exception as e:
        refund.status = 'failed'
        refund.gateway_error = str(e)
        refund.save()
        
        # Log error
        TransactionLog.objects.create(
            gateway='paystack',
            transaction_type='refund',
            request_data={'refund_id': refund.refund_id, 'amount': refund.amount},
            response_data={'error': str(e)},
            is_successful=False,
            error_message=str(e),
        )

@csrf_exempt
@require_POST
def stripe_webhook(request):
    """Handle Stripe webhook events"""
    
    if not hasattr(settings, 'STRIPE_WEBHOOK_SECRET'):
        return HttpResponseBadRequest('Stripe webhook secret not configured')
    
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        return HttpResponseBadRequest(f'Invalid payload: {str(e)}')
    except stripe.error.SignatureVerificationError as e:
        return HttpResponseBadRequest(f'Invalid signature: {str(e)}')
    
    # Handle the event
    event_type = event['type']
    
    try:
        if event_type == 'payment_intent.succeeded':
            payment_intent = event['data']['object']
            handle_payment_intent_succeeded(payment_intent)
        elif event_type == 'payment_intent.payment_failed':
            payment_intent = event['data']['object']
            handle_payment_intent_failed(payment_intent)
        elif event_type == 'charge.refunded':
            charge = event['data']['object']
            handle_charge_refunded(charge)
        elif event_type == 'payment_intent.canceled':
            payment_intent = event['data']['object']
            handle_payment_intent_cancelled(payment_intent)
    
    except Exception as e:
        # Log webhook processing error
        TransactionLog.objects.create(
            gateway='stripe',
            transaction_type='webhook_error',
            request_data=event_type,
            response_data={'error': str(e)},
            is_successful=False,
            error_message=str(e),
        )
        return HttpResponse(status=500)
    
    # Log successful webhook
    TransactionLog.objects.create(
        gateway='stripe',
        transaction_type='webhook',
        request_data=event_type,
        response_data={'status': 'processed'},
        is_successful=True,
    )
    
    return JsonResponse({'status': 'success'})

def handle_payment_intent_succeeded(payment_intent):
    """Handle successful Stripe payment"""
    
    with transaction.atomic():
        try:
            # Find payment by intent ID
            payment = Payment.objects.filter(
                metadata__stripe_intent_id=payment_intent['id']
            ).first()
            
            if not payment and payment_intent.get('metadata'):
                # Try to find by order number
                order_number = payment_intent['metadata'].get('order_number')
                if order_number:
                    payment = Payment.objects.filter(
                        order__order_number=order_number,
                        payment_gateway='stripe',
                        status='pending'
                    ).first()
            
            if payment:
                payment.mark_as_paid(payment_intent['id'])
                payment.gateway_response = payment_intent
                payment.save()
                
                # Update order status
                if payment.order:
                    payment.order.payment_status = 'paid'
                    payment.order.paid_at = timezone.now()
                    payment.order.status = 'confirmed'
                    payment.order.save()
                    
                    # Clear user's cart
                    Cart.objects.filter(user=payment.order.user).delete()
        
        except Exception as e:
            raise e

def handle_payment_intent_failed(payment_intent):
    """Handle failed Stripe payment"""
    
    try:
        payment = Payment.objects.filter(
            metadata__stripe_intent_id=payment_intent['id']
        ).first()
        
        if payment:
            error_message = payment_intent.get('last_payment_error', {}).get('message', 'Payment failed')
            payment.mark_as_failed(error_message)
            payment.gateway_response = payment_intent
            payment.save()
    
    except Exception as e:
        raise e

@csrf_exempt
@require_POST
def paystack_webhook(request):
    """Handle Paystack webhook events"""
    
    # For now, accept all webhooks (in production, verify signature)
    try:
        payload = json.loads(request.body)
        event = payload.get('event', '')
        data = payload.get('data', {})
        
        if event == 'charge.success':
            handle_paystack_charge_success(data)
        elif event == 'charge.failed':
            handle_paystack_charge_failed(data)
        elif event == 'refund.processed':
            handle_paystack_refund_processed(data)
        
        # Log webhook
        TransactionLog.objects.create(
            gateway='paystack',
            transaction_type='webhook',
            request_data=event,
            response_data={'status': 'processed'},
            is_successful=True,
        )
        
        return JsonResponse({'status': 'success'})
    
    except Exception as e:
        TransactionLog.objects.create(
            gateway='paystack',
            transaction_type='webhook_error',
            request_data=str(request.body)[:500],
            response_data={'error': str(e)},
            is_successful=False,
            error_message=str(e),
        )
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

def handle_paystack_charge_success(data):
    """Handle successful Paystack charge"""
    
    with transaction.atomic():
        try:
            reference = data.get('reference')
            
            # Find payment by reference
            payment = Payment.objects.filter(
                gateway_transaction_id=reference
            ).first()
            
            if payment:
                payment.mark_as_paid(reference)
                payment.gateway_response = data
                payment.save()
                
                # Update order status
                if payment.order:
                    payment.order.payment_status = 'paid'
                    payment.order.paid_at = timezone.now()
                    payment.order.status = 'confirmed'
                    payment.order.save()
                    
                    # Clear user's cart
                    Cart.objects.filter(user=payment.order.user).delete()
        
        except Exception as e:
            raise e

@login_required
def payment_success(request, payment_id):
    """Handle successful payment"""
    
    payment = get_object_or_404(Payment, payment_id=payment_id, user=request.user)
    
    if payment.is_successful and payment.order:
        # Update order status if not already updated
        if payment.order.status != 'confirmed':
            payment.order.status = 'confirmed'
            payment.order.save()
        
        context = {
            'payment': payment,
            'order': payment.order,
        }
        return render(request, 'payments/success.html', context)
    else:
        messages.warning(request, 'Payment is still processing. Please check back later.')
        return redirect('orders:order_detail', order_number=payment.order.order_number)

@login_required
def payment_failed(request, payment_id):
    """Handle failed payment"""
    
    payment = get_object_or_404(Payment, payment_id=payment_id, user=request.user)
    
    context = {
        'payment': payment,
        'order': payment.order,
    }
    return render(request, 'payments/failed.html', context)

@login_required
@require_http_methods(["GET", "POST"])
def payment_detail(request, payment_id):
    """View payment details"""
    
    payment = get_object_or_404(Payment, payment_id=payment_id, user=request.user)
    
    if request.method == 'POST' and request.POST.get('action') == 'retry':
        # Retry payment
        return redirect('payments:payment_process', order_id=payment.order.id)
    
    context = {
        'payment': payment,
        'refunds': payment.refunds.all(),
    }
    
    return render(request, 'payments/detail.html', context)

@login_required
@require_POST
def create_refund(request, payment_id):
    """Create refund request"""
    
    payment = get_object_or_404(Payment, payment_id=payment_id, user=request.user)
    
    if not payment.is_refundable:
        messages.error(request, 'This payment cannot be refunded.')
        return redirect('payments:payment_detail', payment_id=payment_id)
    
    amount_str = request.POST.get('amount')
    reason = request.POST.get('reason', 'requested_by_customer')
    description = request.POST.get('description', '')
    
    try:
        # Convert amount to decimal
        refund_amount = Decimal(amount_str) if amount_str else payment.amount
        
        # Validate refund amount
        if refund_amount <= 0:
            messages.error(request, 'Refund amount must be greater than 0.')
            return redirect('payments:payment_detail', payment_id=payment_id)
        
        if refund_amount > payment.amount:
            messages.error(request, 'Refund amount cannot exceed original payment amount.')
            return redirect('payments:payment_detail', payment_id=payment_id)
        
        # Create refund record
        refund = Refund.objects.create(
            payment=payment,
            order=payment.order,
            amount=refund_amount,
            currency=payment.currency,
            reason=reason,
            description=description,
            requested_by=request.user,
        )
        
        # Process refund based on gateway
        if payment.payment_gateway == 'stripe':
            process_stripe_refund(refund)
        elif payment.payment_gateway == 'paystack':
            process_paystack_refund(refund)
        else:
            # Manual refund for other gateways
            refund.status = 'processing'
            refund.save()
            messages.info(request, 'Refund request submitted. Our team will process it manually.')
        
        messages.success(request, 'Refund request submitted successfully.')
    
    except ValueError:
        messages.error(request, 'Invalid refund amount.')
    except Exception as e:
        messages.error(request, f'Refund failed: {str(e)}')
    
    return redirect('payments:payment_detail', payment_id=payment_id)

def process_stripe_refund(refund):
    """Process refund via Stripe"""
    
    try:
        if not stripe.api_key:
            raise Exception('Stripe not configured')
        
        # Create Stripe refund
        stripe_refund = stripe.Refund.create(
            payment_intent=refund.payment.gateway_response.get('intent_id'),
            amount=int(refund.amount * 100),  # Convert to cents
            reason='requested_by_customer',
        )
        
        if stripe_refund.status == 'succeeded':
            refund.mark_as_completed(stripe_refund.id)
            refund.gateway_response = stripe_refund
            
            # Update payment status
            if refund.amount == refund.payment.amount:
                refund.payment.status = 'refunded'
            else:
                refund.payment.status = 'partially_refunded'
            refund.payment.save()
            
            # Update order status
            if refund.order:
                refund.order.status = 'refunded'
                refund.order.save()
            
            # Log transaction
            TransactionLog.objects.create(
                gateway='stripe',
                transaction_type='refund',
                request_data={'refund_id': refund.refund_id, 'amount': refund.amount},
                response_data=stripe_refund,
                is_successful=True,
            )
        else:
            raise Exception(f'Stripe refund status: {stripe_refund.status}')
    
    except Exception as e:
        refund.status = 'failed'
        refund.gateway_error = str(e)
        refund.save()
        
        # Log error
        TransactionLog.objects.create(
            gateway='stripe',
            transaction_type='refund',
            request_data={'refund_id': refund.refund_id, 'amount': refund.amount},
            response_data={'error': str(e)},
            is_successful=False,
            error_message=str(e),
        )

@login_required
def payment_history(request):
    """View user payment history"""
    
    payments = Payment.objects.filter(
        user=request.user
    ).select_related('order').order_by('-created_at')
    
    # Filter by status if provided
    status_filter = request.GET.get('status')
    if status_filter:
        payments = payments.filter(status=status_filter)
    
    # Filter by payment method if provided
    method_filter = request.GET.get('method')
    if method_filter:
        payments = payments.filter(payment_method=method_filter)
    
    # Date range filter
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        payments = payments.filter(created_at__date__gte=date_from)
    if date_to:
        payments = payments.filter(created_at__date__lte=date_to)
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(payments, 10)
    page = request.GET.get('page')
    payments = paginator.get_page(page)
    
    context = {
        'payments': payments,
        'status_choices': Payment.PAYMENT_STATUS_CHOICES,
        'method_choices': Payment.PAYMENT_METHOD_CHOICES,
        'total_paid': sum(p.amount for p in payments if p.is_successful),
    }
    
    return render(request, 'payments/history.html', context)

@login_required
def payment_methods(request):
    """View available payment methods"""
    
    active_gateways = PaymentGatewayConfig.objects.filter(is_active=True)
    
    context = {
        'gateways': active_gateways,
        'stripe_enabled': hasattr(settings, 'STRIPE_PUBLIC_KEY') and settings.STRIPE_PUBLIC_KEY,
        'paystack_enabled': hasattr(settings, 'PAYSTACK_PUBLIC_KEY') and settings.PAYSTACK_PUBLIC_KEY,
    }
    
    return render(request, 'payments/methods.html', context)

@csrf_exempt
@require_GET
def verify_payment(request, payment_id):
    """Verify payment status (AJAX endpoint)"""
    
    try:
        payment = Payment.objects.get(payment_id=payment_id)
        
        return JsonResponse({
            'success': True,
            'payment_id': payment.payment_id,
            'status': payment.status,
            'is_successful': payment.is_successful,
            'amount': str(payment.amount),
            'currency': payment.currency,
        })
    except Payment.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Payment not found'
        }, status=404)
        
# payments/admin_views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from django.db.models import Q, Count, Sum, Avg
from django.utils import timezone
from datetime import datetime, timedelta
from django.urls import reverse
from decimal import Decimal
import json

from .models import Payment, Refund, PaymentGatewayConfig, TransactionLog
from orders.models import Order

def is_admin_or_staff(user):
    """Check if user is admin or staff"""
    return user.is_authenticated and (user.is_staff or user.is_superuser or getattr(user, 'role', '') == 'admin')

@login_required
@user_passes_test(is_admin_or_staff)
def admin_payment_list(request):
    """Admin payment listing"""
    payments = Payment.objects.all().select_related('user', 'order')
    
    # Apply filters
    status_filter = request.GET.get('status', '')
    method_filter = request.GET.get('method', '')
    gateway_filter = request.GET.get('gateway', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    search_query = request.GET.get('q', '')
    
    if status_filter:
        payments = payments.filter(status=status_filter)
    
    if method_filter:
        payments = payments.filter(payment_method=method_filter)
    
    if gateway_filter:
        payments = payments.filter(payment_gateway=gateway_filter)
    
    if date_from:
        try:
            date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            payments = payments.filter(created_at__date__gte=date_from)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            payments = payments.filter(created_at__date__lte=date_to)
        except ValueError:
            pass
    
    if search_query:
        payments = payments.filter(
            Q(payment_id__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(order__order_number__icontains=search_query) |
            Q(gateway_transaction_id__icontains=search_query)
        )
    
    # Payment stats
    payment_stats = {
        'total': Payment.objects.count(),
        'completed': Payment.objects.filter(status='completed').count(),
        'pending': Payment.objects.filter(status='pending').count(),
        'failed': Payment.objects.filter(status='failed').count(),
        'refunded': Payment.objects.filter(status='refunded').count(),
        'today': Payment.objects.filter(created_at__date=timezone.now().date()).count(),
        'week': Payment.objects.filter(created_at__date__gte=timezone.now().date() - timedelta(days=7)).count(),
    }
    
    # Today's revenue
    today_revenue = Payment.objects.filter(
        created_at__date=timezone.now().date(),
        status='completed'
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    # Payment method distribution
    method_dist = Payment.objects.values('payment_method').annotate(
        count=Count('id'),
        total=Sum('amount')
    ).order_by('-count')
    
    # Pagination
    paginator = Paginator(payments.order_by('-created_at'), 20)
    page = request.GET.get('page')
    payments = paginator.get_page(page)
    
    context = {
        'payments': payments,
        'payment_stats': payment_stats,
        'today_revenue': today_revenue,
        'method_dist': method_dist,
        'query_params': request.GET.urlencode(),
    }
    
    return render(request, 'admin/payments/list.html', context)

@login_required
@user_passes_test(is_admin_or_staff)
def admin_payment_detail(request, payment_id):
    """Admin payment detail view"""
    payment = get_object_or_404(Payment, payment_id=payment_id)
    refunds = payment.refunds.all()
    
    context = {
        'payment': payment,
        'refunds': refunds,
        'gateways': PaymentGatewayConfig.objects.all(),
    }
    
    return render(request, 'admin/payments/detail.html', context)

@login_required
@user_passes_test(is_admin_or_staff)
def admin_payment_refund(request, payment_id):
    """Create refund for payment (admin)"""
    payment = get_object_or_404(Payment, payment_id=payment_id)
    
    if request.method == 'POST':
        amount_str = request.POST.get('amount')
        reason = request.POST.get('reason', 'requested_by_customer')
        description = request.POST.get('description', '')
        
        try:
            refund_amount = Decimal(amount_str) if amount_str else payment.amount
            
            # Validate
            if refund_amount <= 0:
                messages.error(request, 'Refund amount must be greater than 0.')
                return redirect('payments:admin_payment_detail', payment_id=payment_id)
            
            # Calculate already refunded amount safely
            already_refunded = payment.refunds.filter(status='completed').aggregate(
                total=Sum('amount')
            )['total'] or Decimal('0')
            
            max_refundable = payment.amount - already_refunded
            
            if refund_amount > max_refundable:
                messages.error(request, f'Refund amount cannot exceed ${max_refundable} (${payment.amount} - ${already_refunded} already refunded).')
                return redirect('payments:admin_payment_detail', payment_id=payment_id)
            
            # Check if already refunded
            if payment.status == 'refunded':
                messages.error(request, 'This payment has already been fully refunded.')
                return redirect('payments:admin_payment_detail', payment_id=payment_id)
            
            # Create refund
            refund = Refund.objects.create(
                payment=payment,
                order=payment.order,
                amount=refund_amount,
                currency=payment.currency,
                reason=reason,
                description=description,
                requested_by=request.user,
                status='processing' if payment.payment_gateway in ['stripe', 'paystack'] else 'pending'
            )
            
            # Try to process refund automatically if supported
            if payment.payment_gateway == 'stripe':
                from .views import process_stripe_refund
                process_stripe_refund(refund)
                if refund.status == 'completed':
                    messages.success(request, f'Refund of ${refund_amount} processed successfully via Stripe.')
                else:
                    messages.warning(request, f'Refund request created but needs manual processing: {refund.gateway_error}')
            elif payment.payment_gateway == 'paystack':
                from .views import process_paystack_refund
                process_paystack_refund(refund)
                if refund.status == 'completed':
                    messages.success(request, f'Refund of ${refund_amount} processed successfully via Paystack.')
                else:
                    messages.warning(request, f'Refund request created but needs manual processing: {refund.gateway_error}')
            else:
                messages.info(request, f'Refund request of ${refund_amount} submitted for manual processing.')
            
            return redirect('payments:admin_payment_detail', payment_id=payment_id)
            
        except ValueError:
            messages.error(request, 'Invalid refund amount.')
        except Exception as e:
            messages.error(request, f'Error creating refund: {str(e)}')
    
    # GET request - show refund form
    # Calculate max refundable amount safely
    already_refunded = payment.refunds.filter(status='completed').aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')
    
    context = {
        'payment': payment,
        'max_refund_amount': payment.amount - already_refunded,
        'already_refunded': already_refunded,
    }
    
    return render(request, 'admin/payments/refund.html', context)


# Update this function in payments/views.py (admin_views section)

@login_required
@user_passes_test(is_admin_or_staff)
def admin_refund_list(request):
    """Admin refund request listing - Payment refunds"""
    from .models import Refund  # Make sure to import from payments models
    from decimal import Decimal
    from django.db.models import Sum
    
    refunds = Refund.objects.all().select_related('payment', 'order', 'requested_by')
    
    # Apply filters
    status_filter = request.GET.get('status', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    search_query = request.GET.get('q', '')
    
    if status_filter:
        refunds = refunds.filter(status=status_filter)
    
    if date_from:
        try:
            date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            refunds = refunds.filter(requested_at__date__gte=date_from)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            refunds = refunds.filter(requested_at__date__lte=date_to)
        except ValueError:
            pass
    
    if search_query:
        refunds = refunds.filter(
            Q(refund_id__icontains=search_query) |
            Q(payment__payment_id__icontains=search_query) |
            Q(requested_by__username__icontains=search_query) |
            Q(order__order_number__icontains=search_query)
        )
    
    # Stats for payment refunds
    refund_stats = {
        'total': refunds.count(),
        'pending': refunds.filter(status='pending').count(),
        'processing': refunds.filter(status='processing').count(),
        'completed': refunds.filter(status='completed').count(),
        'failed': refunds.filter(status='failed').count(),
    }
    
    # Calculate total refunded amount (only completed refunds)
    total_refunded_amount = refunds.filter(status='completed').aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')
    
    # Pagination
    paginator = Paginator(refunds.order_by('-requested_at'), 20)
    page = request.GET.get('page')
    refunds = paginator.get_page(page)
    
    context = {
        'refunds': refunds,
        'refund_stats': refund_stats,
        'total_refunded_amount': total_refunded_amount,
    }
    
    return render(request, 'admin/payments/refund_list.html', context)

@login_required
@user_passes_test(is_admin_or_staff)
def admin_refund_detail(request, refund_id):
    """Admin refund request detail"""
    refund = get_object_or_404(Refund, id=refund_id)
    
    context = {
        'refund': refund,
        'refund_status_choices': Refund.REFUND_STATUS_CHOICES, 
        
    }
    
    return render(request, 'admin/payments/refund_detail.html', context)

@login_required
@user_passes_test(is_admin_or_staff)
def admin_update_refund_status(request, refund_id):
    """Update refund request status (admin)"""
    if request.method == 'POST':
        refund = get_object_or_404(Refund, id=refund_id)
        new_status = request.POST.get('status')
        
        if new_status in dict(Refund.REFUND_STATUS_CHOICES):
            old_status = refund.status
            refund.status = new_status
            
            # Update completed status
            if new_status == 'completed' and not refund.is_completed:
                refund.is_completed = True
                refund.processed_at = timezone.now()
                
                # Update payment status
                total_refunded = refund.payment.refunds.filter(status='completed').aggregate(total=Sum('amount'))['total'] or 0
                if total_refunded >= refund.payment.amount:
                    refund.payment.status = 'refunded'
                else:
                    refund.payment.status = 'partially_refunded'
                refund.payment.save()
            
            # Update order status if fully refunded
            if new_status == 'completed' and refund.order:
                total_refunded = refund.payment.refunds.filter(status='completed').aggregate(total=Sum('amount'))['total'] or 0
                if total_refunded >= refund.payment.amount:
                    refund.order.status = 'refunded'
                    refund.order.save()
            
            refund.save()
            messages.success(request, f'Refund status updated to {refund.get_status_display()}')
        else:
            messages.error(request, 'Invalid status')
    
    return redirect('payments:admin_refund_detail', refund_id=refund_id)


@login_required
@user_passes_test(is_admin_or_staff)
def admin_gateway_list(request):
    """Admin payment gateway configuration"""
    gateways = PaymentGatewayConfig.objects.all()
    
    context = {
        'gateways': gateways,
    }
    
    return render(request, 'admin/payments/gateway_list.html', context)

@login_required
@user_passes_test(is_admin_or_staff)
def admin_gateway_detail(request, gateway_id):
    """Admin gateway detail"""
    gateway = get_object_or_404(PaymentGatewayConfig, id=gateway_id)
    
    context = {
        'gateway': gateway,
    }
    
    return render(request, 'admin/payments/gateway_detail.html', context)

@login_required
@user_passes_test(is_admin_or_staff)
def admin_gateway_edit(request, gateway_id):
    """Edit payment gateway configuration"""
    gateway = get_object_or_404(PaymentGatewayConfig, id=gateway_id)
    
    if request.method == 'POST':
        gateway.is_active = request.POST.get('is_active') == 'on'
        gateway.is_test_mode = request.POST.get('is_test_mode') == 'on'
        gateway.api_key = request.POST.get('api_key', '')
        gateway.secret_key = request.POST.get('secret_key', '')
        gateway.webhook_secret = request.POST.get('webhook_secret', '')
        
        # Parse JSON fields
        try:
            gateway.supported_currencies = json.loads(request.POST.get('supported_currencies', '[]'))
            gateway.supported_countries = json.loads(request.POST.get('supported_countries', '[]'))
            gateway.payment_methods = json.loads(request.POST.get('payment_methods', '[]'))
        except json.JSONDecodeError:
            pass
        
        gateway.transaction_fee_percent = request.POST.get('transaction_fee_percent', '2.9')
        gateway.transaction_fee_fixed = request.POST.get('transaction_fee_fixed', '0.30')
        
        gateway.save()
        messages.success(request, f'{gateway.get_name_display()} configuration updated.')
        return redirect('payments:admin_gateway_detail', gateway_id=gateway.id)
    
    context = {
        'gateway': gateway,
    }
    
    return render(request, 'admin/payments/gateway_edit.html', context)

@login_required
@user_passes_test(is_admin_or_staff)
def admin_transaction_logs(request):
    """View transaction logs"""
    logs = TransactionLog.objects.all().order_by('-created_at')
    
    # Apply filters
    gateway_filter = request.GET.get('gateway', '')
    type_filter = request.GET.get('type', '')
    success_filter = request.GET.get('success', '')
    
    if gateway_filter:
        logs = logs.filter(gateway=gateway_filter)
    
    if type_filter:
        logs = logs.filter(transaction_type=type_filter)
    
    if success_filter:
        logs = logs.filter(is_successful=(success_filter == 'true'))
    
    # Pagination
    paginator = Paginator(logs, 50)
    page = request.GET.get('page')
    logs = paginator.get_page(page)
    
    context = {
        'logs': logs,
        'gateway_choices': TransactionLog.objects.values_list('gateway', flat=True).distinct(),
        'type_choices': TransactionLog.objects.values_list('transaction_type', flat=True).distinct(),
    }
    
    return render(request, 'admin/payments/transaction_logs.html', context)

@login_required
@user_passes_test(is_admin_or_staff)
def admin_payment_dashboard(request):
    """Payments dashboard for admin"""
    
    # Date ranges
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    
    # Payment stats
    today_payments = Payment.objects.filter(created_at__date=today)
    today_revenue = today_payments.filter(status='completed').aggregate(total=Sum('amount'))['total'] or 0
    
    week_payments = Payment.objects.filter(created_at__date__gte=week_ago)
    week_revenue = week_payments.filter(status='completed').aggregate(total=Sum('amount'))['total'] or 0
    
    month_payments = Payment.objects.filter(created_at__date__gte=month_ago)
    month_revenue = month_payments.filter(status='completed').aggregate(total=Sum('amount'))['total'] or 0
    
    # Payment status distribution
    status_dist = Payment.objects.values('status').annotate(
        count=Count('id'),
        total=Sum('amount')
    ).order_by('status')
    
    # Payment method distribution
    method_dist = Payment.objects.values('payment_method').annotate(
        count=Count('id'),
        total=Sum('amount')
    ).order_by('-total')
    
    # Recent payments
    recent_payments = Payment.objects.select_related('user', 'order').order_by('-created_at')[:10]
    
    # Gateway performance
    gateway_perf = Payment.objects.values('payment_gateway').annotate(
        count=Count('id'),
        success_count=Count('id', filter=Q(status='completed')),
        total=Sum('amount'),
        avg_amount=Avg('amount')
    ).order_by('-total')
    
    context = {
        'today_payments_count': today_payments.count(),
        'today_revenue': today_revenue,
        'week_payments_count': week_payments.count(),
        'week_revenue': week_revenue,
        'month_payments_count': month_payments.count(),
        'month_revenue': month_revenue,
        'status_dist': status_dist,
        'method_dist': method_dist,
        'gateway_perf': gateway_perf,
        'recent_payments': recent_payments,
        'today': today,
    }
    
    return render(request, 'admin/payments/dashboard.html', context)

@login_required
@user_passes_test(is_admin_or_staff)
def export_payments_csv(request):
    """Export payments as CSV"""
    import csv
    from django.http import HttpResponse
    
    # Get filter parameters
    status_filter = request.GET.get('status', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    payments = Payment.objects.all().select_related('user', 'order')
    
    if status_filter:
        payments = payments.filter(status=status_filter)
    
    if date_from:
        try:
            date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            payments = payments.filter(created_at__date__gte=date_from)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            payments = payments.filter(created_at__date__lte=date_to)
        except ValueError:
            pass
    
    # Create HTTP response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="payments_export.csv"'
    
    writer = csv.writer(response)
    
    # Write header
    writer.writerow([
        'Payment ID', 'Date', 'User', 'Email', 'Order Number',
        'Amount', 'Currency', 'Payment Method', 'Gateway', 'Status',
        'Transaction ID', 'Paid At'
    ])
    
    # Write data
    for payment in payments:
        writer.writerow([
            payment.payment_id,
            payment.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            payment.user.username if payment.user else '',
            payment.customer_email,
            payment.order.order_number if payment.order else '',
            str(payment.amount),
            payment.currency,
            payment.get_payment_method_display(),
            payment.payment_gateway,
            payment.get_status_display(),
            payment.gateway_transaction_id or '',
            payment.paid_at.strftime('%Y-%m-%d %H:%M:%S') if payment.paid_at else ''
        ])
    
    return response


@login_required
@user_passes_test(is_admin_or_staff)
def download_payment_details(request, payment_id):
    """Download individual payment details as PDF/CSV"""
    payment = get_object_or_404(Payment, payment_id=payment_id)
    
    # For now, just redirect to detail page or create a simple CSV
    # You can implement PDF generation here using reportlab or weasyprint
    
    import csv
    from django.http import HttpResponse
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="payment_{payment_id}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Payment ID', payment.payment_id])
    writer.writerow(['Date', payment.created_at.strftime('%Y-%m-%d %H:%M:%S')])
    writer.writerow(['Customer Email', payment.customer_email])
    writer.writerow(['Amount', f"${payment.amount}"])
    writer.writerow(['Currency', payment.currency])
    writer.writerow(['Payment Method', payment.get_payment_method_display()])
    writer.writerow(['Gateway', payment.payment_gateway])
    writer.writerow(['Status', payment.get_status_display()])
    writer.writerow(['Transaction ID', payment.gateway_transaction_id or ''])
    writer.writerow(['Paid At', payment.paid_at.strftime('%Y-%m-%d %H:%M:%S') if payment.paid_at else ''])
    
    return response