from django.core.management.base import BaseCommand
from notifications.models import NotificationTemplate


class Command(BaseCommand):
    help = 'Set up default notification templates'
    
    def handle(self, *args, **options):
        templates_data = [
            # Test Templates
            {
                'name': 'test_notification',
                'template_type': 'email',
                'category': 'system',
                'subject': 'Test Email Notification',
                'html_content': '''
                    <h2>Test Email Notification</h2>
                    <p>Hello {{ user.first_name|default:user.username }},</p>
                    <p>This is a test email notification sent at {{ timestamp|date:"Y-m-d H:i:s" }}</p>
                    <p>If you received this, email notifications are working correctly!</p>
                    <p>Best regards,<br>TechStore Team</p>
                ''',
                'text_content': 'Test Email Notification - Sent at {{ timestamp|date:"Y-m-d H:i:s" }}',
                'push_content': 'Test notification sent successfully',
                'is_active': True,
            },
            # Order Confirmation
            {
                'name': 'order_confirmation',
                'template_type': 'email',
                'category': 'order',
                'subject': 'Order Confirmation - #{{ order_id }}',
                'html_content': '''
                    <h2>Order Confirmed!</h2>
                    <p>Hi {{ user.first_name|default:user.username }},</p>
                    <p>Thank you for your order. Your order has been received and is being processed.</p>
                    <p><strong>Order ID:</strong> {{ order_id }}</p>
                    <p><strong>Order Date:</strong> {{ order_date|date:"M d, Y" }}</p>
                    <p><strong>Total Amount:</strong> ${{ total_amount }}</p>
                    <p>We will notify you as soon as your order is shipped.</p>
                    <p>Best regards,<br>TechStore Team</p>
                ''',
                'text_content': 'Order Confirmation #{{ order_id }} - Total: ${{ total_amount }}',
                'push_content': 'Your order #{{ order_id }} has been confirmed',
                'is_active': True,
            },
            # Payment Confirmation
            {
                'name': 'payment_confirmation',
                'template_type': 'email',
                'category': 'payment',
                'subject': 'Payment Successful - Order #{{ order_id }}',
                'html_content': '''
                    <h2>Payment Confirmed!</h2>
                    <p>Hi {{ user.first_name|default:user.username }},</p>
                    <p>Your payment has been received successfully.</p>
                    <p><strong>Order ID:</strong> {{ order_id }}</p>
                    <p><strong>Amount Paid:</strong> ${{ amount }}</p>
                    <p><strong>Payment Method:</strong> {{ payment_method }}</p>
                    <p><strong>Transaction ID:</strong> {{ transaction_id }}</p>
                    <p>Thank you for your purchase!</p>
                    <p>Best regards,<br>TechStore Team</p>
                ''',
                'text_content': 'Payment Confirmation - Order #{{ order_id }} - Amount: ${{ amount }}',
                'push_content': 'Payment received for order #{{ order_id }}',
                'is_active': True,
            },
            # Shipping Notification
            {
                'name': 'shipping_notification',
                'template_type': 'email',
                'category': 'shipping',
                'subject': 'Your Order is On the Way - #{{ order_id }}',
                'html_content': '''
                    <h2>Your Order is Shipping!</h2>
                    <p>Hi {{ user.first_name|default:user.username }},</p>
                    <p>Great news! Your order is on the way.</p>
                    <p><strong>Order ID:</strong> {{ order_id }}</p>
                    <p><strong>Tracking Number:</strong> {{ tracking_number }}</p>
                    <p><strong>Carrier:</strong> {{ carrier }}</p>
                    <p><strong>Estimated Delivery:</strong> {{ estimated_delivery|date:"M d, Y" }}</p>
                    <p><a href="{{ tracking_url }}">Track Your Package</a></p>
                    <p>Best regards,<br>TechStore Team</p>
                ''',
                'text_content': 'Your order #{{ order_id }} is shipping. Track: {{ tracking_number }}',
                'push_content': 'Your order is on the way! Tracking: {{ tracking_number }}',
                'is_active': True,
            },
            # SMS Templates
            {
                'name': 'test_notification',
                'template_type': 'sms',
                'category': 'system',
                'subject': 'Test SMS',
                'text_content': 'Test SMS from TechStore. If you received this, SMS notifications work!',
                'is_active': True,
            },
            {
                'name': 'order_confirmation',
                'template_type': 'sms',
                'category': 'order',
                'subject': 'Order Confirmation',
                'text_content': 'Order #{{ order_id }} confirmed! Total: ${{ total_amount }}. Thank you!',
                'is_active': True,
            },
            {
                'name': 'payment_confirmation',
                'template_type': 'sms',
                'category': 'payment',
                'subject': 'Payment Confirmed',
                'text_content': 'Payment of ${{ amount }} received for order #{{ order_id }}. Thank you!',
                'is_active': True,
            },
            {
                'name': 'shipping_notification',
                'template_type': 'sms',
                'category': 'shipping',
                'subject': 'Shipping Update',
                'text_content': 'Order #{{ order_id }} shipped! Track: {{ tracking_number }}',
                'is_active': True,
            },
        ]
        
        created_count = 0
        updated_count = 0
        
        for template_data in templates_data:
            template, created = NotificationTemplate.objects.get_or_create(
                name=template_data['name'],
                template_type=template_data['template_type'],
                defaults={
                    'category': template_data['category'],
                    'subject': template_data.get('subject', ''),
                    'html_content': template_data.get('html_content', ''),
                    'text_content': template_data.get('text_content', ''),
                    'push_content': template_data.get('push_content', ''),
                    'is_active': template_data.get('is_active', True),
                    'available_variables': ['user', 'site_name', 'order_id', 'amount', 'tracking_number'],
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Created template: {template.name} ({template.get_template_type_display()})')
                )
            else:
                updated_count += 1
                self.stdout.write(f'✓ Template already exists: {template.name}')
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Setup complete! Created {created_count} templates, {updated_count} already existed.'))
