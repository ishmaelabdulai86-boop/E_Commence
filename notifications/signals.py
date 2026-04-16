from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
import logging

from orders.models import Order
from payments.models import Payment
from .models import NotificationPreference
from .services import OrderNotificationService, AccountNotificationService

logger = logging.getLogger(__name__)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_notification_preferences(sender, instance, created, **kwargs):
    """Create notification preferences when a new user is created"""
    
    if created:
        try:
            NotificationPreference.objects.create(user=instance)
            
            # Send welcome email
            notification_service = AccountNotificationService()
            notification_service.send_welcome_email(instance)
        except Exception as e:
            logger.error(f"Error creating notification preferences for user {instance.username}: {str(e)}", exc_info=True)


@receiver(post_save, sender=Order)
def handle_order_created(sender, instance, created, **kwargs):
    """Send notifications when order is created or updated"""
    
    try:
        if created:
            # Order created - send confirmation email
            logger.info(f"New order created: {instance.order_number}. Sending confirmation email...")
            notification_service = OrderNotificationService()
            notification_service.send_order_confirmation(instance)
        else:
            # Order updated - check if status changed
            if 'update_fields' in kwargs:
                update_fields = kwargs.get('update_fields')
                if update_fields and 'status' in update_fields:
                    # Status was updated
                    logger.info(f"Order status changed to {instance.status}. Sending status update email...")
                    notification_service = OrderNotificationService()
                    
                    if instance.status == 'shipped':
                        notification_service.send_shipping_update(instance)
                    elif instance.status == 'delivered':
                        notification_service.send_delivery_confirmation(instance)
    except Exception as e:
        logger.error(f"Error handling order signal for {instance.order_number}: {str(e)}", exc_info=True)


@receiver(post_save, sender=Payment)
def handle_payment_status(sender, instance, created, **kwargs):
    """Send notifications when payment status changes"""
    
    try:
        # Check if status was updated and is completed
        if not created and instance.status == 'completed':
            if 'update_fields' in kwargs:
                update_fields = kwargs.get('update_fields')
                if update_fields and 'status' in update_fields:
                    logger.info(f"Payment completed: {instance.payment_id}. Sending confirmation email...")
                    notification_service = OrderNotificationService()
                    notification_service.send_payment_confirmation(instance)
    except Exception as e:
        logger.error(f"Error handling payment signal for {instance.payment_id}: {str(e)}", exc_info=True)