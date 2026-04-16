"""
Orders services - Email and notification utilities
"""
import logging
from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def send_order_confirmation_email(order):
    """Send order confirmation email to customer"""
    try:
        logger.info(f"Sending order confirmation email for order {order.order_number} to {order.user.email}")
        
        # Prepare email context
        context = {
            'order': order,
            'order_items': order.items.select_related('product').all(),
            'customer_name': order.user.first_name or order.user.username,
            'order_url': f"{settings.SITE_URL}/orders/{order.order_number}/" if hasattr(settings, 'SITE_URL') else '#',
        }
        
        # Render email template
        html_message = render_to_string('orders/emails/order_confirmation.html', context)
        plain_message = render_to_string('orders/emails/order_confirmation_text.txt', context)
        
        # Create email
        subject = f"Order Confirmation - {order.order_number}"
        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[order.user.email]
        )
        email.attach_alternative(html_message, "text/html")
        
        # Send email
        result = email.send(fail_silently=False)
        logger.info(f"Order confirmation email sent successfully for order {order.order_number}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error sending order confirmation email for order {order.order_number}: {str(e)}", exc_info=True)
        return False


def send_order_shipped_email(order, tracking_number=None):
    """Send order shipped notification email"""
    try:
        context = {
            'order': order,
            'tracking_number': tracking_number,
            'customer_name': order.user.first_name or order.user.username,
        }
        
        html_message = render_to_string('orders/emails/order_shipped.html', context)
        plain_message = render_to_string('orders/emails/order_shipped_text.txt', context)
        
        subject = f"Your Order is On Its Way - {order.order_number}"
        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[order.user.email]
        )
        email.attach_alternative(html_message, "text/html")
        email.send(fail_silently=False)
        
        return True
        
    except Exception as e:
        print(f"Error sending order shipped email: {str(e)}")
        return False


def send_order_delivered_email(order):
    """Send order delivered notification email"""
    try:
        context = {
            'order': order,
            'customer_name': order.user.first_name or order.user.username,
        }
        
        html_message = render_to_string('orders/emails/order_delivered.html', context)
        plain_message = render_to_string('orders/emails/order_delivered_text.txt', context)
        
        subject = f"Your Order Has Been Delivered - {order.order_number}"
        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[order.user.email]
        )
        email.attach_alternative(html_message, "text/html")
        email.send(fail_silently=False)
        
        return True
        
    except Exception as e:
        print(f"Error sending order delivered email: {str(e)}")
        return False


def send_order_status_update_email(order, old_status, new_status):
    """Send order status update notification email to customer"""
    try:
        context = {
            'order': order,
            'old_status': dict(order._meta.get_field('status').choices).get(old_status, old_status),
            'new_status': dict(order._meta.get_field('status').choices).get(new_status, new_status),
            'customer_name': order.user.first_name or order.user.username,
        }
        
        html_message = render_to_string('orders/emails/order_status_update.html', context)
        plain_message = render_to_string('orders/emails/order_status_update_text.txt', context)
        
        subject = f"Your Order Status Updated - {order.order_number}"
        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[order.user.email]
        )
        email.attach_alternative(html_message, "text/html")
        email.send(fail_silently=False)
        
        return True
        
    except Exception as e:
        print(f"Error sending order status update email: {str(e)}")
        return False


def send_payment_status_update_email(order, old_status, new_status):
    """Send payment status update notification email to customer"""
    try:
        context = {
            'order': order,
            'old_status': dict(order._meta.get_field('payment_status').choices).get(old_status, old_status),
            'new_status': dict(order._meta.get_field('payment_status').choices).get(new_status, new_status),
            'customer_name': order.user.first_name or order.user.username,
        }
        
        html_message = render_to_string('orders/emails/payment_status_update.html', context)
        plain_message = render_to_string('orders/emails/payment_status_update_text.txt', context)
        
        subject = f"Payment Status Updated - {order.order_number}"
        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[order.user.email]
        )
        email.attach_alternative(html_message, "text/html")
        email.send(fail_silently=False)
        
        return True
        
    except Exception as e:
        print(f"Error sending payment status update email: {str(e)}")
        return False
