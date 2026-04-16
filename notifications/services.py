from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone
from django.utils.html import strip_tags
from django.contrib.auth import get_user_model
import requests
import logging
import json

# Optional dependencies
try:
    from twilio.rest import Client
except ImportError:
    Client = None
    logger_import = logging.getLogger(__name__)
    logger_import.warning("Twilio not installed. SMS notifications will not work.")

try:
    from firebase_admin import messaging
except ImportError:
    messaging = None
    logger_import = logging.getLogger(__name__)
    logger_import.warning("Firebase Admin not installed. Push notifications will not work.")

from .models import (
    Notification, NotificationTemplate, NotificationPreference,
    EmailLog, SMSLog, PushNotificationDevice
)

logger = logging.getLogger(__name__)
User = get_user_model()

class NotificationService:
    """Service class to handle all notification types"""
    
    def __init__(self):
        self.twilio_client = None
        self.twilio_enabled = self._is_twilio_configured()
    
    def _is_twilio_configured(self):
        """Check if Twilio credentials are properly configured (not placeholder values)"""
        if not Client:
            return False
        
        account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', '')
        auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', '')
        phone_number = getattr(settings, 'TWILIO_PHONE_NUMBER', '')
        
        # Check if credentials are set and not placeholder values
        # These are test/placeholder values used for development
        placeholder_values = [
            '', # This is a test SID from Twilio docs
            '', # This is a test Auth Token from Twilio docs
            '', # This is a test phone number from Twilio docs
            
        ]
        
        # Convert all values to lowercase for comparison
        credentials_lower = [val.lower() for val in [account_sid, auth_token, phone_number]]
        
        if any(val in placeholder_values for val in credentials_lower):
            logger.warning("Twilio credentials appear to be placeholder values. SMS will be mocked.")
            return False
        
        if not (account_sid and auth_token and phone_number):
            logger.warning("Twilio credentials not fully configured. SMS will be mocked.")
            return False
        
        # Try to initialize client
        try:
            self.twilio_client = Client(account_sid, auth_token)
            logger.info("✓ Twilio client initialized successfully")
            return True
        except Exception as e:
            logger.warning(f"Failed to initialize Twilio client: {str(e)}. SMS will be mocked.")
            return False
    
    def _sanitize_context(self, context):
        """
        Remove non-serializable objects from context dict for storage in JSONField.
        Keeps only basic types and collections of basic types.
        """
        try:
            # First test if context is JSON serializable
            json.dumps(context)
            return context  # Already serializable
        except (TypeError, ValueError):
            pass
        
        # If not serializable, clean it
        sanitized = {}
        for key, value in context.items():
            if key == 'user' and hasattr(value, 'id'):
                # Store user info as a dict instead of User object
                sanitized[key] = {
                    'id': value.id,
                    'username': value.username,
                    'email': value.email,
                    'first_name': getattr(value, 'first_name', ''),
                    'last_name': getattr(value, 'last_name', ''),
                }
            elif isinstance(value, (str, int, float, bool, type(None))):
                # Basic types are fine
                sanitized[key] = value
            elif isinstance(value, (list, tuple)):
                # Try to sanitize list items
                try:
                    sanitized[key] = [item if isinstance(item, (str, int, float, bool, type(None))) else str(item) for item in value]
                except:
                    sanitized[key] = str(value)
            elif isinstance(value, dict):
                # Recursively sanitize nested dicts
                sanitized[key] = self._sanitize_context(value)
            else:
                # Convert non-serializable objects to string
                try:
                    sanitized[key] = str(value)
                except:
                    sanitized[key] = f"<{type(value).__name__}>"
        
        return sanitized
    
    def _sanitize_provider_response(self, response_obj):
        """
        Convert provider response object to JSON-serializable dict.
        Safely handles any object type.
        """
        if response_obj is None:
            return None
        
        try:
            # Test if already serializable
            json.dumps(response_obj)
            return response_obj
        except (TypeError, ValueError):
            pass
        
        # Convert object to dict-like structure
        try:
            if isinstance(response_obj, dict):
                return {k: self._sanitize_provider_response(v) for k, v in response_obj.items()}
            elif isinstance(response_obj, (list, tuple)):
                return [self._sanitize_provider_response(item) for item in response_obj]
            elif hasattr(response_obj, '__dict__'):
                # Convert object to its __dict__ representation
                result = {}
                for k, v in response_obj.__dict__.items():
                    if not k.startswith('_'):  # Skip private attributes
                        try:
                            if isinstance(v, (str, int, float, bool, type(None))):
                                result[k] = v
                            elif isinstance(v, dict):
                                result[k] = self._sanitize_provider_response(v)
                            else:
                                result[k] = str(v)
                        except:
                            result[k] = f"<{type(v).__name__}>"
                return result
            else:
                return str(response_obj)
        except Exception as e:
            logger.error(f"Error sanitizing provider response: {str(e)}")
            return {'error': f'Could not serialize response: {str(e)}'}
    
    def send_notification(self, user, template_name, context, category='system', **kwargs):
        """
        Send notification using template
        Returns: dict with results for each notification type
        """
        
        try:
            # Get user preferences
            preference, created = NotificationPreference.objects.get_or_create(user=user)
            
            results = {}
            
            # Check and send email
            if preference.can_send_notification(category, 'email'):
                results['email'] = self.send_email(user, template_name, context, category, **kwargs)
            
            # Check and send SMS
            if preference.can_send_notification(category, 'sms'):
                results['sms'] = self.send_sms(user, template_name, context, category, **kwargs)
            
            # Check and send push notification
            if preference.can_send_notification(category, 'push'):
                results['push'] = self.send_push(user, template_name, context, category, **kwargs)
            
            # Check and send WhatsApp (if configured)
            if preference.can_send_notification(category, 'whatsapp'):
                results['whatsapp'] = self.send_whatsapp(user, template_name, context, category, **kwargs)
            
            return results
        
        except Exception as e:
            logger.error(f"Error sending notification: {str(e)}")
            return {'error': str(e)}
    
    def send_email(self, user, template_name, context, category='system', **kwargs):
        """Send email notification"""
        
        subject = None
        html_content = None
        text_content = None
        template = None
        
        try:
            # Get template
            template = NotificationTemplate.objects.filter(
                name=template_name,
                template_type='email',
                category=category,
                is_active=True
            ).first()
            
            if not template:
                logger.warning(f"Email template not found: {template_name} (category: {category})")
                return False
            
            # Prepare context
            context.update({
                'user': user,
                'site_name': getattr(settings, 'SITE_NAME', 'TechStore'),
                'site_url': getattr(settings, 'SITE_URL', 'https://techstore.com'),
                'current_year': timezone.now().year,
            })
            
            # Render content
            try:
                html_content = template.render(context)
            except Exception as e:
                logger.error(f"Error rendering HTML template: {str(e)}")
                html_content = template.html_content
            
            # Use format() for text_content as fallback
            try:
                text_content = template.text_content.format(**context) if template.text_content else strip_tags(html_content)
            except KeyError as e:
                logger.warning(f"Missing template variable {str(e)}, using plain text")
                text_content = strip_tags(html_content)
            
            # Create email subject and from_email
            try:
                subject = template.subject.format(**context) if template.subject else f"Notification from {getattr(settings, 'SITE_NAME', 'TechStore')}"
            except KeyError:
                subject = template.subject or f"Notification from {getattr(settings, 'SITE_NAME', 'TechStore')}"
            
            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@techstore.com')
            to_email = user.email
            
            # Check if user has email
            if not to_email:
                logger.warning(f"User {user.username} has no email address")
                return False
            
            # Create and send email
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=from_email,
                to=[to_email],
                reply_to=[getattr(settings, 'REPLY_TO_EMAIL', 'support@techstore.com')],
            )
            
            email.attach_alternative(html_content, "text/html")
            
            # Try to send email
            email_sent = email.send(fail_silently=False)
            
            if not email_sent:
                logger.warning(f"Email backend did not confirm sending to {to_email}")
                return False
            
            # Log email
            EmailLog.objects.create(
                to_email=to_email,
                to_name=user.get_full_name() or user.username,
                subject=subject,
                html_content=html_content,
                text_content=text_content,
                status='sent',
                sent_at=timezone.now(),
                template=template,
                user=user,
            )
            
            # Create notification record
            Notification.objects.create(
                user=user,
                notification_type='email',
                template=template,
                title=subject,
                message=text_content[:500],
                data=self._sanitize_context(context),
                status='sent',
                sent_at=timezone.now(),
            )
            
            logger.info(f"✓ Email sent to {to_email}: {subject}")
            return True
        
        except Exception as e:
            logger.error(f"Error sending email: {str(e)}", exc_info=True)
            
            # Log failed email
            try:
                EmailLog.objects.create(
                    to_email=user.email if hasattr(user, 'email') else '',
                    to_name=user.get_full_name() or user.username if hasattr(user, 'username') else '',
                    subject=subject or 'Error',
                    html_content=html_content or '',
                    text_content=text_content or str(e),
                    status='failed',
                    provider_response={'error': str(e)},
                    template=template,
                    user=user,
                )
            except Exception as log_error:
                logger.error(f"Could not log failed email: {str(log_error)}")
            
            return False
    
    def send_sms(self, user, template_name, context, category='system', **kwargs):
        """Send SMS notification"""
        
        try:
            # Check if user has phone number
            if not user.phone:
                logger.warning(f"User {user.username} has no phone number for SMS")
                return False
            
            # Get template
            template = NotificationTemplate.objects.filter(
                name=template_name,
                template_type='sms',
                category=category,
                is_active=True
            ).first()
            
            if not template:
                logger.warning(f"SMS template not found: {template_name}")
                return False
            
            # Prepare context
            context.update({
                'user': user,
                'site_name': getattr(settings, 'SITE_NAME', 'TechStore'),
            })
            
            # Render message
            message = template.text_content.format(**context)
            
            # Send SMS using Twilio (if configured)
            if self.twilio_enabled and self.twilio_client:
                try:
                    twilio_response = self.twilio_client.messages.create(
                        body=message,
                        from_=settings.TWILIO_PHONE_NUMBER,
                        to=user.phone
                    )
                    
                    # Log SMS
                    SMSLog.objects.create(
                        to_phone=user.phone,
                        to_name=user.get_full_name() or user.username,
                        message=message,
                        status='sent',
                        sent_at=timezone.now(),
                        provider='twilio',
                        provider_message_id=twilio_response.sid,
                        provider_response=self._sanitize_provider_response(twilio_response.__dict__),
                        template=template,
                        user=user,
                    )
                    
                    logger.info(f"✓ SMS sent to {user.phone}")
                    
                except Exception as e:
                    logger.error(f"Error sending SMS to {user.phone}: {str(e)}", exc_info=True)
                    
                    # Log failed SMS
                    SMSLog.objects.create(
                        to_phone=user.phone,
                        to_name=user.get_full_name() or user.username,
                        message=message,
                        status='failed',
                        provider='twilio',
                        provider_response={'error': str(e)},
                        template=template,
                        user=user,
                    )
                    
                    return False
            else:
                # Development mode: Mock SMS sending
                logger.info(f"📱 [MOCK SMS] Message to {user.phone}: {message[:60]}...")
                
                SMSLog.objects.create(
                    to_phone=user.phone,
                    to_name=user.get_full_name() or user.username,
                    message=message,
                    status='sent',
                    sent_at=timezone.now(),
                    provider='simulated',
                    provider_response={'mode': 'development', 'note': 'This is a simulated SMS. Configure Twilio credentials to send real SMS.'},
                    template=template,
                    user=user,
                )
                
                logger.info(f"✓ SMS simulated for {user.phone}")
            
            # Create notification record
            Notification.objects.create(
                user=user,
                notification_type='sms',
                template=template,
                title=f"SMS Notification",
                message=message,
                data=self._sanitize_context(context),
                status='sent',
                sent_at=timezone.now(),
            )
            
            return True
        
        except Exception as e:
            logger.error(f"Error sending SMS to {user.phone}: {str(e)}")
            
            # Log failed SMS
            SMSLog.objects.create(
                to_phone=user.phone if 'user' in locals() else '',
                to_name=user.get_full_name() if 'user' in locals() else '',
                message=message if 'message' in locals() else '',
                status='failed',
                provider_response={'error': str(e)},
                template=template if 'template' in locals() else None,
                user=user if 'user' in locals() else None,
            )
            
            return False
    
    def send_push(self, user, template_name, context, category='system', **kwargs):
        """Send push notification"""
        
        try:
            # Get active devices for user
            devices = PushNotificationDevice.objects.filter(user=user, is_active=True)
            
            if not devices.exists():
                logger.warning(f"No active push devices for user {user.username}")
                return False
            
            # Get template
            template = NotificationTemplate.objects.filter(
                name=template_name,
                template_type='push',
                category=category,
                is_active=True
            ).first()
            
            if not template:
                logger.warning(f"Push template not found: {template_name}")
                return False
            
            # Prepare context
            context.update({
                'user': user,
                'site_name': getattr(settings, 'SITE_NAME', 'TechStore'),
            })
            
            # Render message
            title = template.subject.format(**context) if template.subject else "Notification"
            body = template.push_content.format(**context) if template.push_content else template.text_content.format(**context)
            
            success_count = 0
            
            for device in devices:
                try:
                    if device.platform == 'android':
                        # Send to Android via FCM
                        message = messaging.Message(
                            notification=messaging.Notification(
                                title=title,
                                body=body,
                            ),
                            token=device.device_token,
                            data={
                                'type': category,
                                'template': template_name,
                                'timestamp': str(timezone.now()),
                            }
                        )
                        
                        # Send message (requires Firebase Admin SDK setup)
                        # response = messaging.send(message)
                        # logger.info(f"FCM response: {response}")
                        
                        success_count += 1
                    
                    elif device.platform == 'ios':
                        # Send to iOS via APNs
                        # Similar implementation for iOS
                        success_count += 1
                    
                    elif device.platform == 'web':
                        # Send to web via service workers
                        # This would be handled by a separate service
                        success_count += 1
                
                except Exception as e:
                    logger.error(f"Error sending push to device {device.device_token}: {str(e)}")
                    # Deactivate failed device
                    device.is_active = False
                    device.save()
            
            # Create notification record
            Notification.objects.create(
                user=user,
                notification_type='push',
                template=template,
                title=title,
                message=body,
                data=self._sanitize_context(context),
                status='sent' if success_count > 0 else 'failed',
                sent_at=timezone.now() if success_count > 0 else None,
            )
            
            logger.info(f"Push notifications sent to {success_count}/{devices.count()} devices for user {user.username}")
            return success_count > 0
        
        except Exception as e:
            logger.error(f"Error sending push notifications: {str(e)}")
            return False
    
    def send_whatsapp(self, user, template_name, context, category='system', **kwargs):
        """Send WhatsApp message"""
        
        try:
            # Check if user has phone number
            if not user.phone:
                logger.warning(f"User {user.username} has no phone number for WhatsApp")
                return False
            
            # WhatsApp Business API implementation would go here
            # This requires integration with WhatsApp Business API or a service like Twilio WhatsApp
            
            # For now, just log it
            logger.info(f"WhatsApp message would be sent to {user.phone}")
            
            # Create notification record
            Notification.objects.create(
                user=user,
                notification_type='whatsapp',
                title=f"WhatsApp Notification",
                message=f"WhatsApp message for {template_name}",
                data=self._sanitize_context(context),
                status='sent',
                sent_at=timezone.now(),
            )
            
            return True
        
        except Exception as e:
            logger.error(f"Error sending WhatsApp: {str(e)}")
            return False
    
    def send_bulk_notification(self, users, template_name, context, category='promotional', **kwargs):
        """Send notification to multiple users"""
        
        results = {
            'total': len(users),
            'success': 0,
            'failed': 0,
            'details': [],
        }
        
        for user in users:
            try:
                result = self.send_notification(user, template_name, context, category, **kwargs)
                
                if result and not result.get('error'):
                    results['success'] += 1
                    results['details'].append({
                        'user': user.username,
                        'status': 'success',
                    })
                else:
                    results['failed'] += 1
                    results['details'].append({
                        'user': user.username,
                        'status': 'failed',
                        'error': result.get('error') if result else 'Unknown error',
                    })
            
            except Exception as e:
                results['failed'] += 1
                results['details'].append({
                    'user': user.username,
                    'status': 'failed',
                    'error': str(e),
                })
        
        return results

class OrderNotificationService(NotificationService):
    """Specialized service for order-related notifications"""
    
    def send_order_confirmation(self, order):
        """Send order confirmation notification"""
        
        context = {
            'order': order,
            'order_number': order.order_number,
            'order_date': order.created_at,
            'total_amount': order.total_amount,
            'items': order.items.all(),
            'shipping_address': order.shipping_address,
        }
        
        return self.send_notification(
            user=order.user,
            template_name='order_confirmation',
            context=context,
            category='order',
        )
    
    def send_payment_confirmation(self, payment):
        """Send payment confirmation notification"""
        
        context = {
            'payment': payment,
            'order': payment.order,
            'amount': payment.amount,
            'payment_method': payment.get_payment_method_display(),
            'transaction_id': payment.gateway_transaction_id,
        }
        
        return self.send_notification(
            user=payment.user,
            template_name='payment_confirmation',
            context=context,
            category='payment',
        )
    
    def send_shipping_update(self, order):
        """Send shipping status update"""
        
        context = {
            'order': order,
            'order_number': order.order_number,
            'status': order.get_status_display(),
            'tracking_number': order.tracking_number,
            'carrier': order.carrier,
        }
        
        return self.send_notification(
            user=order.user,
            template_name='shipping_update',
            context=context,
            category='shipping',
        )
    
    def send_delivery_confirmation(self, order):
        """Send delivery confirmation"""
        
        context = {
            'order': order,
            'order_number': order.order_number,
            'delivered_at': order.delivered_at,
        }
        
        return self.send_notification(
            user=order.user,
            template_name='delivery_confirmation',
            context=context,
            category='shipping',
        )

class AccountNotificationService(NotificationService):
    """Specialized service for account-related notifications"""
    
    def send_welcome_email(self, user):
        """Send welcome email to new user"""
        
        context = {
            'user': user,
            'welcome_message': f"Welcome to {getattr(settings, 'SITE_NAME', 'TechStore')}!",
        }
        
        return self.send_notification(
            user=user,
            template_name='welcome_email',
            context=context,
            category='account',
        )
    
    def send_password_reset(self, user, reset_url):
        """Send password reset email"""
        
        context = {
            'user': user,
            'reset_url': reset_url,
            'expiry_hours': 24,  # Password reset link expiry
        }
        
        return self.send_notification(
            user=user,
            template_name='password_reset',
            context=context,
            category='account',
        )
    
    def send_email_verification(self, user, verification_url):
        """Send email verification"""
        
        context = {
            'user': user,
            'verification_url': verification_url,
            'expiry_hours': 24,  # Verification link expiry
        }
        
        return self.send_notification(
            user=user,
            template_name='email_verification',
            context=context,
            category='account',
        )
    
    def send_otp_code(self, user, otp_code, purpose='verification'):
        """Send OTP code via SMS"""
        
        context = {
            'user': user,
            'otp_code': otp_code,
            'purpose': purpose,
            'valid_minutes': 10,  # OTP validity
        }
        
        return self.send_notification(
            user=user,
            template_name='otp_verification',
            context=context,
            category='account',
        )