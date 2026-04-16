from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from notifications.services import NotificationService
import logging

User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Test email and SMS functionality'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--test-type',
            type=str,
            choices=['email', 'smtp', 'sms', 'all'],
            default='all',
            help='Type of test to run'
        )
        parser.add_argument(
            '--user',
            type=int,
            help='User ID to send test to'
        )
    
    def handle(self, *args, **options):
        test_type = options['test_type']
        user_id = options['user']
        
        # Get test user
        if user_id:
            try:
                test_user = User.objects.get(pk=user_id)
            except User.DoesNotExist:
                raise CommandError(f'User with ID {user_id} not found')
        else:
            test_user = User.objects.first()
            if not test_user:
                raise CommandError('No users found in database')
        
        self.stdout.write(self.style.SUCCESS('=== Notification System Test ===\n'))
        
        # Test configurations
        if test_type in ['smtp', 'email', 'all']:
            self.test_smtp_config()
            self.test_email_send(test_user)
        
        if test_type in ['sms', 'all']:
            self.test_sms_config()
        
        self.stdout.write(self.style.SUCCESS('\n✓ Tests completed!'))
    
    def test_smtp_config(self):
        """Test SMTP configuration"""
        self.stdout.write('\n--- SMTP Configuration ---')
        
        email_backend = getattr(settings, 'EMAIL_BACKEND', None)
        email_host = getattr(settings, 'EMAIL_HOST', None)
        email_port = getattr(settings, 'EMAIL_PORT', None)
        email_use_tls = getattr(settings, 'EMAIL_USE_TLS', None)
        email_host_user = getattr(settings, 'EMAIL_HOST_USER', None)
        default_from = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
        
        self.stdout.write(f'Email Backend: {email_backend}')
        self.stdout.write(f'SMTP Host: {email_host}')
        self.stdout.write(f'SMTP Port: {email_port}')
        self.stdout.write(f'Use TLS: {email_use_tls}')
        self.stdout.write(f'Host User: {email_host_user}')
        self.stdout.write(f'Default From: {default_from}')
        
        if not all([email_backend, email_host, email_port, email_host_user]):
            self.stdout.write(self.style.WARNING('⚠ SMTP configuration incomplete!'))
        else:
            self.stdout.write(self.style.SUCCESS('✓ SMTP configuration looks good'))
    
    def test_email_send(self, user):
        """Test actual email sending"""
        self.stdout.write('\n--- Testing Email Send ---')
        
        if not user.email:
            self.stdout.write(self.style.ERROR('✗ User has no email address'))
            return
        
        self.stdout.write(f'Sending test email to: {user.email}')
        
        try:
            # Try simple send_mail first
            subject = '[TechStore] Test Email'
            message = f'Hello {user.first_name or user.username},\n\nThis is a test email from TechStore.\n\nIf you received this, email is working!\n\nBest regards,\nTechStore Team'
            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@techstore.com')
            
            result = send_mail(
                subject,
                message,
                from_email,
                [user.email],
                fail_silently=False,
            )
            
            if result:
                self.stdout.write(self.style.SUCCESS('✓ Test email sent successfully!'))
                logger.info(f"Test email sent to {user.email}")
            else:
                self.stdout.write(self.style.WARNING('⚠ Email backend returned 0 (not sent)'))
        
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Error sending email: {str(e)}'))
            logger.error(f"Error in email test: {str(e)}", exc_info=True)
    
    def test_sms_config(self):
        """Test SMS configuration"""
        self.stdout.write('\n--- SMS Configuration (Twilio) ---')
        
        twilio_account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', None)
        twilio_auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', None)
        twilio_phone = getattr(settings, 'TWILIO_PHONE_NUMBER', None)
        
        if not all([twilio_account_sid, twilio_auth_token, twilio_phone]):
            if twilio_account_sid == 'your_twilio_account_sid':
                self.stdout.write(self.style.WARNING('⚠ Twilio not configured (using placeholders)'))
            else:
                self.stdout.write(self.style.WARNING('⚠ Twilio configuration incomplete'))
        else:
            self.stdout.write(self.style.SUCCESS('✓ Twilio is configured'))
            self.stdout.write(f'Account SID: {twilio_account_sid[:10]}...')
            self.stdout.write(f'Phone Number: {twilio_phone}')
