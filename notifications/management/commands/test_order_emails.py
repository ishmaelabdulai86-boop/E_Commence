"""
Management command to test order email notifications
"""
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from orders.models import Order
from notifications.services import OrderNotificationService
import logging

User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Test order email notifications'
    
    def add_arguments(self, parser):
        parser.add_argument(
            'order_id',
            type=int,
            help='Order ID to test notifications for'
        )
        
        parser.add_argument(
            '--type',
            type=str,
            default='confirmation',
            help='Type of notification: confirmation, shipped, delivered, payment',
            choices=['confirmation', 'shipped', 'delivered', 'payment']
        )
    
    def handle(self, *args, **options):
        try:
            order_id = options['order_id']
            notification_type = options['type']
            
            # Get the order
            order = Order.objects.get(id=order_id)
            self.stdout.write(f'Testing {notification_type} email for order {order.order_number}...')
            
            service = OrderNotificationService()
            
            if notification_type == 'confirmation':
                success = service.send_order_confirmation(order)
                message = 'Order confirmation email'
            elif notification_type == 'shipped':
                success = service.send_shipping_update(order)
                message = 'Shipping update email'
            elif notification_type == 'delivered':
                success = service.send_delivery_confirmation(order)
                message = 'Delivery confirmation email'
            elif notification_type == 'payment':
                # Get the associated payment
                payment = order.payments.filter(status='completed').first()
                if not payment:
                    raise CommandError(f'No completed payment found for order {order.order_number}')
                success = service.send_payment_confirmation(payment)
                message = 'Payment confirmation email'
            
            if success:
                self.stdout.write(
                    self.style.SUCCESS(f'✓ {message} sent successfully to {order.user.email}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'✗ {message} failed to send')
                )
                
        except Order.DoesNotExist:
            raise CommandError(f'Order with ID {order_id} does not exist')
        except Exception as e:
            raise CommandError(f'Error testing notification: {str(e)}')
