from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.utils import timezone
from notifications.models import NotificationTemplate, Notification
from notifications.services import NotificationService
import json

User = get_user_model()


class Command(BaseCommand):
    help = 'Test notification system by sending test notifications'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            type=int,
            help='User ID to send notification to'
        )
        parser.add_argument(
            '--type',
            type=str,
            choices=['email', 'sms', 'push', 'in_app'],
            default='email',
            help='Notification type (default: email)'
        )
        parser.add_argument(
            '--template',
            type=str,
            help='Template name to use'
        )
        parser.add_argument(
            '--list',
            action='store_true',
            help='List available templates'
        )
        parser.add_argument(
            '--users',
            action='store_true',
            help='List available users'
        )
        parser.add_argument(
            '--data',
            type=str,
            help='JSON data to pass to template'
        )
    
    def handle(self, *args, **options):
        # List templates
        if options['list']:
            self.list_templates()
            return
        
        # List users
        if options['users']:
            self.list_users()
            return
        
        # Validate inputs
        if not options['user']:
            raise CommandError('--user is required')
        
        try:
            user = User.objects.get(pk=options['user'])
        except User.DoesNotExist:
            raise CommandError(f'User with ID {options["user"]} not found')
        
        notification_type = options['type']
        template_name = options['template'] or 'test_notification'
        
        # Parse data
        test_data = {}
        if options['data']:
            try:
                test_data = json.loads(options['data'])
            except json.JSONDecodeError:
                raise CommandError('Invalid JSON in --data')
        
        # Create test context
        context = {
            'user': user,
            'test': True,
            'timestamp': timezone.now(),
            **test_data
        }
        
        # Send notification
        self.stdout.write(f'Sending {notification_type} notification to {user.username}...')
        
        try:
            if notification_type == 'in_app':
                # Create in-app notification directly
                template, created = NotificationTemplate.objects.get_or_create(
                    name=template_name,
                    template_type='push',
                    defaults={'category': 'system', 'is_active': True}
                )
                
                Notification.objects.create(
                    user=user,
                    notification_type='in_app',
                    template=template,
                    title='Test Notification',
                    message=f'Test in-app notification sent at {timezone.now()}',
                    data={'test': True, **test_data},
                    status='sent',
                    sent_at=timezone.now(),
                )
                success = True
            else:
                notification_service = NotificationService()
                
                if notification_type == 'email':
                    success = notification_service.send_email(
                        user=user,
                        template_name=template_name,
                        context=context,
                        category='system'
                    )
                elif notification_type == 'sms':
                    success = notification_service.send_sms(
                        user=user,
                        template_name=template_name,
                        context=context,
                        category='system'
                    )
                else:  # push
                    success = notification_service.send_push(
                        user=user,
                        template_name=template_name,
                        context=context,
                        category='system'
                    )
            
            if success:
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Test {notification_type} notification sent to {user.username}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'✓ Notification processed (but may not have been delivered)')
                )
        
        except Exception as e:
            raise CommandError(f'Error sending notification: {str(e)}')
    
    def list_templates(self):
        """List all available notification templates"""
        templates = NotificationTemplate.objects.filter(is_active=True).order_by('category', 'name')
        
        self.stdout.write(self.style.SUCCESS('Available Templates:'))
        self.stdout.write('-' * 80)
        
        for template in templates:
            status = '✓' if template.is_active else '✗'
            self.stdout.write(
                f'{status} {template.name:30} | {template.get_template_type_display():15} | {template.get_category_display()}'
            )
        
        self.stdout.write('-' * 80)
        self.stdout.write(f'Total: {templates.count()} templates')
    
    def list_users(self):
        """List recent users"""
        users = User.objects.all().order_by('-date_joined')[:10]
        
        self.stdout.write(self.style.SUCCESS('Recent Users:'))
        self.stdout.write('-' * 80)
        
        for user in users:
            email = user.email or 'no email'
            self.stdout.write(f'ID: {user.id:5} | {user.username:20} | {user.get_full_name:20} | {email}')
        
        self.stdout.write('-' * 80)
