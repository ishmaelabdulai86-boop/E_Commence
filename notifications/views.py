from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q
import json
from django.utils import timezone
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Q, Max
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
import logging
from .models import Notification, NotificationPreference, PushNotificationDevice, NotificationTemplate, EmailLog, SMSLog
from .services import NotificationService

# Get custom User model
User = get_user_model()

@login_required
def notification_list(request):
    """List user notifications"""
    
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')
    
    # Filter by type if provided
    notification_type = request.GET.get('type')
    if notification_type:
        notifications = notifications.filter(notification_type=notification_type)
    
    # Filter by read status
    read_status = request.GET.get('read')
    if read_status == 'read':
        notifications = notifications.filter(is_read=True)
    elif read_status == 'unread':
        notifications = notifications.filter(is_read=False)
    
    # Pagination
    paginator = Paginator(notifications, 20)
    page = request.GET.get('page')
    notifications = paginator.get_page(page)
    
    # Mark notifications as read when viewing
    if request.GET.get('mark_read') == 'true':
        unread_notifications = notifications.filter(is_read=False)
        unread_notifications.update(is_read=True, status='read')
    
    context = {
        'notifications': notifications,
        'unread_count': Notification.objects.filter(user=request.user, is_read=False).count(),
    }
    
    return render(request, 'notifications/list.html', context)

@login_required
def mark_as_read(request, notification_id):
    """Mark a notification as read"""
    
    notification = get_object_or_404(Notification, notification_id=notification_id, user=request.user)
    notification.mark_as_read()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True})
    
    messages.success(request, 'Notification marked as read.')
    return redirect('notification_list')

@login_required
def mark_all_as_read(request):
    """Mark all notifications as read"""
    
    Notification.objects.filter(user=request.user, is_read=False).update(
        is_read=True,
        status='read',
        read_at=timezone.now()
    )
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True})
    
    messages.success(request, 'All notifications marked as read.')
    return redirect('notification_list')

@login_required
def notification_preferences(request):
    """Manage notification preferences"""
    
    preference, created = NotificationPreference.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        # Update email preferences
        preference.email_order_updates = request.POST.get('email_order_updates') == 'on'
        preference.email_payment_updates = request.POST.get('email_payment_updates') == 'on'
        preference.email_shipping_updates = request.POST.get('email_shipping_updates') == 'on'
        preference.email_promotions = request.POST.get('email_promotions') == 'on'
        preference.email_account_updates = request.POST.get('email_account_updates') == 'on'
        
        # Update SMS preferences
        preference.sms_order_updates = request.POST.get('sms_order_updates') == 'on'
        preference.sms_payment_updates = request.POST.get('sms_payment_updates') == 'on'
        preference.sms_shipping_updates = request.POST.get('sms_shipping_updates') == 'on'
        preference.sms_promotions = request.POST.get('sms_promotions') == 'on'
        
        # Update push preferences
        preference.push_order_updates = request.POST.get('push_order_updates') == 'on'
        preference.push_payment_updates = request.POST.get('push_payment_updates') == 'on'
        preference.push_shipping_updates = request.POST.get('push_shipping_updates') == 'on'
        preference.push_promotions = request.POST.get('push_promotions') == 'on'
        
        # Update WhatsApp preferences
        preference.whatsapp_order_updates = request.POST.get('whatsapp_order_updates') == 'on'
        preference.whatsapp_payment_updates = request.POST.get('whatsapp_payment_updates') == 'on'
        preference.whatsapp_shipping_updates = request.POST.get('whatsapp_shipping_updates') == 'on'
        preference.whatsapp_promotions = request.POST.get('whatsapp_promotions') == 'on'
        
        # Global settings
        preference.do_not_disturb = request.POST.get('do_not_disturb') == 'on'
        
        # Quiet hours
        quiet_start = request.POST.get('quiet_hours_start')
        quiet_end = request.POST.get('quiet_hours_end')
        
        if quiet_start and quiet_end:
            from datetime import datetime as dt
            try:
                preference.quiet_hours_start = dt.strptime(quiet_start, '%H:%M').time()
                preference.quiet_hours_end = dt.strptime(quiet_end, '%H:%M').time()
            except:
                pass
        
        preference.save()
        messages.success(request, 'Notification preferences updated successfully.')
        return redirect('notifications:notification_preferences')
    
    context = {
        'preference': preference,
    }
    
    return render(request, 'admin/notifications/preferences_list.html', context)

@login_required
def register_push_device(request):
    """Register device for push notifications"""
    
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            data = json.loads(request.body)
            
            device_token = data.get('device_token')
            platform = data.get('platform', 'web')
            device_model = data.get('device_model', '')
            os_version = data.get('os_version', '')
            app_version = data.get('app_version', '')
            
            if not device_token:
                return JsonResponse({'success': False, 'error': 'Device token required'})
            
            # Check if device already registered
            device, created = PushNotificationDevice.objects.get_or_create(
                device_token=device_token,
                defaults={
                    'user': request.user,
                    'platform': platform,
                    'device_model': device_model,
                    'os_version': os_version,
                    'app_version': app_version,
                }
            )
            
            if not created:
                # Update existing device
                device.user = request.user
                device.platform = platform
                device.device_model = device_model
                device.os_version = os_version
                device.app_version = app_version
                device.is_active = True
                device.save()
            
            logger.info(f"Device registered for user {request.user.username}: {platform}")
            return JsonResponse({'success': True, 'created': created})
        
        except json.JSONDecodeError:
            logger.error("Invalid JSON in register_push_device request")
            return JsonResponse({'success': False, 'error': 'Invalid JSON'})
        except Exception as e:
            logger.error(f"Error in register_push_device: {str(e)}", exc_info=True)
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request'})

@login_required
def unregister_push_device(request):
    """Unregister device for push notifications"""
    
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            data = json.loads(request.body)
            device_token = data.get('device_token')
            
            if not device_token:
                return JsonResponse({'success': False, 'error': 'Device token required'})
            
            # Deactivate device
            PushNotificationDevice.objects.filter(
                device_token=device_token,
                user=request.user
            ).update(is_active=False)
            
            logger.info(f"Device unregistered for user {request.user.username}")
            return JsonResponse({'success': True})
        
        except json.JSONDecodeError:
            logger.error("Invalid JSON in unregister_push_device request")
            return JsonResponse({'success': False, 'error': 'Invalid JSON'})
        except Exception as e:
            logger.error(f"Error in unregister_push_device: {str(e)}", exc_info=True)
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request'})

@login_required
def test_notification(request):
    """Send a test notification to the user"""
    
    if request.method == 'POST':
        notification_type = request.POST.get('notification_type', 'email')
        category = request.POST.get('category', 'system')
        
        # Create test notification
        notification_service = NotificationService()
        
        context = {
            'user': request.user,
            'test': True,
            'timestamp': timezone.now(),
        }
        
        if notification_type == 'email':
            success = notification_service.send_email(
                user=request.user,
                template_name='test_notification',
                context=context,
                category=category,
            )
        elif notification_type == 'sms':
            success = notification_service.send_sms(
                user=request.user,
                template_name='test_notification',
                context=context,
                category=category,
            )
        elif notification_type == 'push':
            success = notification_service.send_push(
                user=request.user,
                template_name='test_notification',
                context=context,
                category=category,
            )
        else:
            messages.error(request, 'Invalid notification type.')
            return redirect('notifications:notification_preferences')
        
        if success:
            messages.success(request, f'Test {notification_type} notification sent successfully!')
        else:
            messages.error(request, f'Failed to send test {notification_type} notification.')
        
        return redirect('notifications:notification_preferences')
    
    return redirect('notifications:notification_preferences')

def web_push_subscribe(request):
    """Handle web push subscription"""
    
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            from django.contrib.auth.models import AnonymousUser
            
            if isinstance(request.user, AnonymousUser):
                return JsonResponse({'success': False, 'error': 'Authentication required'})
            
            data = json.loads(request.body)
            subscription_info = data.get('subscription')
            
            if not subscription_info:
                return JsonResponse({'success': False, 'error': 'Subscription info required'})
            
            # Store subscription in user's session or database
            # This is a simplified version - in production, use a proper storage
            
            request.session['web_push_subscription'] = subscription_info
            
            return JsonResponse({'success': True})
        
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request'})

@login_required
def get_unread_count(request):
    """API endpoint to get unread notification count"""
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return JsonResponse({'success': True, 'count': count})
    
    return JsonResponse({'success': False, 'error': 'Invalid request'})


@staff_member_required
def api_search_users(request):
    """API endpoint to search for users (excluding staff)"""
    
    if request.method == 'GET':
        search_query = request.GET.get('q', '').strip()
        
        if not search_query or len(search_query) < 2:
            return JsonResponse({
                'success': False,
                'error': 'Query must be at least 2 characters'
            })
        
        # Search for users by username or email (excluding staff)
        users = User.objects.filter(
            is_active=True,
            is_staff=False
        ).filter(
            Q(username__icontains=search_query) | 
            Q(email__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query)
        ).values('id', 'username', 'email', 'first_name', 'last_name')[:20]
        
        users_list = list(users)
        for user in users_list:
            # Create display name
            full_name = f"{user['first_name']} {user['last_name']}".strip()
            user['display_name'] = full_name if full_name else user['username']
        
        return JsonResponse({
            'success': True,
            'users': users_list
        })
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})


@staff_member_required
def api_template_preview(request, template_id):
    """API endpoint to get template preview content"""
    
    try:
        template = NotificationTemplate.objects.get(id=template_id)
        
        return JsonResponse({
            'success': True,
            'template': {
                'id': template.id,
                'name': template.name,
                'type': template.get_template_type_display(),
                'category': template.get_category_display(),
                'subject': template.subject,
                'html_content': template.html_content,
                'text_content': template.text_content,
                'push_content': template.push_content,
            }
        })
    except NotificationTemplate.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Template not found'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


# Admin Notification Dashboard
@staff_member_required
def admin_notification_dashboard(request):
    """Admin dashboard for notifications"""
    
    # Get SMS provider status
    service = NotificationService()
    sms_provider_status = {
        'enabled': service.twilio_enabled,
        'provider': 'Twilio' if service.twilio_enabled else 'Simulated (Development Mode)',
        'account_sid': getattr(settings, 'TWILIO_ACCOUNT_SID', 'Not set')[:10] + '...' if getattr(settings, 'TWILIO_ACCOUNT_SID', '') and len(getattr(settings, 'TWILIO_ACCOUNT_SID', '')) > 10 else 'Not set',
        'phone_number': getattr(settings, 'TWILIO_PHONE_NUMBER', 'Not set'),
    }
    
    # Statistics
    stats = {
        'total_notifications': Notification.objects.count(),
        'unread_notifications': Notification.objects.filter(is_read=False).count(),
        'sent_today': Notification.objects.filter(
            sent_at__date=timezone.now().date()
        ).count(),
        'failed_notifications': Notification.objects.filter(status='failed').count(),
        'total_users_with_notifications': Notification.objects.values('user').distinct().count(),
        'recent_notifications': Notification.objects.order_by('-created_at')[:10],
    }
    
    # Chart data (last 30 days)
    thirty_days_ago = timezone.now() - timezone.timedelta(days=30)
    
    notification_trends = Notification.objects.filter(
        created_at__gte=thirty_days_ago
    ).extra({
        'date': "DATE(created_at)"
    }).values('date').annotate(
        count=Count('id'),
        email_count=Count('id', filter=Q(notification_type='email')),
        sms_count=Count('id', filter=Q(notification_type='sms')),
        push_count=Count('id', filter=Q(notification_type='push'))
    ).order_by('date')
    
    # Top notification types
    notification_by_type = Notification.objects.values(
        'notification_type'
    ).annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Top notification categories
    notification_by_category = Notification.objects.filter(
        template__isnull=False
    ).values(
        'template__category'
    ).annotate(
        count=Count('id')
    ).order_by('-count')
    
    context = {
        'stats': stats,
        'notification_trends': list(notification_trends),
        'notification_by_type': list(notification_by_type),
        'notification_by_category': list(notification_by_category),
        'sms_provider_status': sms_provider_status,
    }
    
    return render(request, 'admin/notifications/dashboard.html', context)

@staff_member_required
def admin_notification_list(request):
    """Admin view for all notifications"""
    
    notifications = Notification.objects.all().order_by('-created_at')
    
    # Filters
    notification_type = request.GET.get('type')
    if notification_type:
        notifications = notifications.filter(notification_type=notification_type)
    
    status = request.GET.get('status')
    if status:
        notifications = notifications.filter(status=status)
    
    user_id = request.GET.get('user')
    if user_id:
        notifications = notifications.filter(user_id=user_id)
    
    search_query = request.GET.get('q')
    if search_query:
        notifications = notifications.filter(
            Q(title__icontains=search_query) |
            Q(message__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__email__icontains=search_query)
        )
    
    # Date filters
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if date_from:
        notifications = notifications.filter(created_at__gte=date_from)
    if date_to:
        notifications = notifications.filter(created_at__lte=date_to)
    
    # Pagination
    paginator = Paginator(notifications, 50)
    page = request.GET.get('page')
    
    try:
        notifications = paginator.page(page)
    except PageNotAnInteger:
        notifications = paginator.page(1)
    except EmptyPage:
        notifications = paginator.page(paginator.num_pages)
    
    context = {
        'notifications': notifications,
        'total_count': paginator.count,
        'notification_types': Notification.NOTIFICATION_TYPE_CHOICES,
        'status_choices': Notification.NOTIFICATION_STATUS_CHOICES,
        'filter_params': request.GET,
    }
    
    return render(request, 'admin/notifications/notification_list.html', context)

@staff_member_required
def admin_notification_detail(request, notification_id):
    """Admin view for notification detail"""
    
    notification = get_object_or_404(Notification, notification_id=notification_id)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'mark_as_read' and not notification.is_read:
            notification.mark_as_read()
            messages.success(request, 'Notification marked as read.')
        elif action == 'mark_as_unread' and notification.is_read:
            notification.is_read = False
            notification.status = 'delivered'
            notification.read_at = None
            notification.save()
            messages.success(request, 'Notification marked as unread.')
        elif action == 'resend':
            # Resend logic (simplified - would need proper resend logic)
            notification.retry_count += 1
            notification.save()
            messages.info(request, 'Resend functionality would be implemented here.')
        
        return redirect('notifications:admin_notification_detail', notification_id=notification_id)
    
    context = {
        'notification': notification,
    }
    
    return render(request, 'admin/notifications/notification_detail.html', context)

@staff_member_required
def admin_template_list(request):
    """Admin view for notification templates"""
    
    templates = NotificationTemplate.objects.all().order_by('-updated_at')
    
    # Filters
    template_type = request.GET.get('type')
    if template_type:
        templates = templates.filter(template_type=template_type)
    
    category = request.GET.get('category')
    if category:
        templates = templates.filter(category=category)
    
    is_active = request.GET.get('is_active')
    if is_active == 'true':
        templates = templates.filter(is_active=True)
    elif is_active == 'false':
        templates = templates.filter(is_active=False)
    
    search_query = request.GET.get('q')
    if search_query:
        templates = templates.filter(
            Q(name__icontains=search_query) |
            Q(subject__icontains=search_query)
        )
    
    # Pagination
    paginator = Paginator(templates, 25)
    page = request.GET.get('page')
    
    try:
        templates = paginator.page(page)
    except PageNotAnInteger:
        templates = paginator.page(1)
    except EmptyPage:
        templates = paginator.page(paginator.num_pages)
    
    context = {
        'templates': templates,
        'template_types': NotificationTemplate.TEMPLATE_TYPE_CHOICES,
        'categories': NotificationTemplate.NOTIFICATION_CATEGORY_CHOICES,
        'filter_params': request.GET,
    }
    
    return render(request, 'admin/notifications/template_list.html', context)

@staff_member_required
def admin_template_detail(request, template_id):
    """Admin view for template detail and editing"""
    
    template = get_object_or_404(NotificationTemplate, id=template_id)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'update':
            template.name = request.POST.get('name', template.name)
            template.subject = request.POST.get('subject', template.subject)
            template.html_content = request.POST.get('html_content', template.html_content)
            template.text_content = request.POST.get('text_content', template.text_content)
            template.push_content = request.POST.get('push_content', template.push_content)
            template.is_active = request.POST.get('is_active') == 'on'
            template.priority = int(request.POST.get('priority', template.priority))
            template.save()
            messages.success(request, 'Template updated successfully.')
        
        elif action == 'preview':
            # Preview logic
            preview_context = {
                'user': request.user,
                'site_name': getattr(settings, 'SITE_NAME', 'TechStore'),
                'site_url': getattr(settings, 'SITE_URL', 'https://techstore.com'),
                'current_year': timezone.now().year,
                'order_number': 'ORD-12345',
                'order_date': timezone.now(),
                'total_amount': 299.99,
            }
            
            try:
                preview_content = template.render(preview_context)
                context['preview_content'] = preview_content
            except Exception as e:
                messages.error(request, f'Preview error: {str(e)}')
        
        return redirect('admin_template_detail', template_id=template_id)
    
    # Get usage statistics
    usage_stats = Notification.objects.filter(template=template).aggregate(
        total_used=Count('id'),
        last_used=Max('created_at')
    )
    
    context = {
        'template': template,
        'usage_stats': usage_stats,
        'available_variables_json': json.dumps(template.available_variables),
    }
    
    return render(request, 'admin/notifications/template_detail.html', context)


@staff_member_required
def admin_template_add(request):
    """Admin view for adding a new notification template"""
    
    if request.method == 'POST':
        try:
            # Extract form data
            name = request.POST.get('name')
            template_type = request.POST.get('template_type')
            category = request.POST.get('category')
            subject = request.POST.get('subject')
            html_content = request.POST.get('html_content')
            text_content = request.POST.get('text_content')
            push_content = request.POST.get('push_content')
            is_active = request.POST.get('is_active') == 'on'
            priority = int(request.POST.get('priority', 1))
            
            # Validate required fields
            if not name or not template_type or not category:
                messages.error(request, 'Name, type, and category are required.')
                return redirect('admin_template_add')
            
            # Check if template with same name and type already exists
            if NotificationTemplate.objects.filter(name=name, template_type=template_type).exists():
                messages.error(request, 'A template with this name and type already exists.')
                return redirect('notifications:admin_template_add')
            
            # Create the template
            template = NotificationTemplate.objects.create(
                name=name,
                template_type=template_type,
                category=category,
                subject=subject or '',
                html_content=html_content or '',
                text_content=text_content or '',
                push_content=push_content or '',
                is_active=is_active,
                priority=priority,
                available_variables=[
                    'user',
                    'site_name',
                    'site_url',
                    'current_year',
                    'order_number',
                    'order_date',
                    'total_amount',
                ]
            )
            
            messages.success(request, f'Template "{name}" created successfully.')
            return redirect('admin_template_detail', template_id=template.id)
        
        except Exception as e:
            logger.error(f"Error creating template: {str(e)}", exc_info=True)
            messages.error(request, f'Error creating template: {str(e)}')
            return redirect('notifications:admin_template_add')
    
    # GET request - show form
    context = {
        'template_types': NotificationTemplate.TEMPLATE_TYPE_CHOICES,
        'categories': NotificationTemplate.NOTIFICATION_CATEGORY_CHOICES,
        'default_variables': [
            'user',
            'site_name',
            'site_url',
            'current_year',
            'order_number',
            'order_date',
            'total_amount',
            'shipping_address',
            'billing_address',
            'tracking_number',
            'courier_name',
            'estimated_delivery',
        ]
    }
    
    return render(request, 'admin/notifications/template_add.html', context)

@staff_member_required
def admin_email_logs(request):
    """Admin view for email logs"""
    
    # Start with base queryset
    email_logs = EmailLog.objects.all().order_by('-created_at')
    
    # Apply filters BEFORE pagination
    status = request.GET.get('status')
    if status:
        email_logs = email_logs.filter(status=status)
    
    to_email = request.GET.get('to_email')
    if to_email:
        email_logs = email_logs.filter(to_email__icontains=to_email)
    
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if date_from:
        email_logs = email_logs.filter(created_at__gte=date_from)
    if date_to:
        email_logs = email_logs.filter(created_at__lte=date_to)
    
    # Search
    search_query = request.GET.get('q')
    if search_query:
        email_logs = email_logs.filter(
            Q(subject__icontains=search_query) |
            Q(to_email__icontains=search_query) |
            Q(to_name__icontains=search_query)
        )
    
    # Get statistics BEFORE pagination
    stats = {
        'total': email_logs.count(),
        'sent': email_logs.filter(status='sent').count(),
        'failed': email_logs.filter(status='failed').count(),
        'delivered': email_logs.filter(status='delivered').count(),
    }
    
    # Pagination - AFTER all filters
    paginator = Paginator(email_logs, 50)
    page = request.GET.get('page')
    
    try:
        email_logs_page = paginator.page(page)
    except PageNotAnInteger:
        email_logs_page = paginator.page(1)
    except EmptyPage:
        email_logs_page = paginator.page(paginator.num_pages)
    
    context = {
        'email_logs': email_logs_page,  # Use paginated object
        'stats': stats,
        'status_choices': EmailLog.STATUS_CHOICES,
        'filter_params': request.GET,
    }
    
    return render(request, 'admin/notifications/email_logs.html', context)


@staff_member_required
def api_retry_email(request):
    """API endpoint to retry sending a failed email"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        email_id = data.get('email_id')
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    if not email_id:
        return JsonResponse({'error': 'Missing email_id'}, status=400)
    
    try:
        email_log = EmailLog.objects.get(id=email_id)
    except EmailLog.DoesNotExist:
        return JsonResponse({'error': 'Email not found'}, status=404)
    
    # Only allow retrying failed emails
    if email_log.status != 'failed':
        return JsonResponse({'error': f'Cannot retry email with status: {email_log.status}'}, status=400)
    
    try:
        # Get user from email log
        user = email_log.user
        if not user:
            return JsonResponse({'error': 'No user associated with this email'}, status=400)
        
        # Get template from email log
        if not email_log.template:
            return JsonResponse({'error': 'No template associated with this email'}, status=400)
        
        template_name = email_log.template.name
        category = email_log.template.category
        
        # Create context for resend
        context = {
            'to_email': email_log.to_email,
            'to_name': email_log.to_name,
            'user_email': user.email,
        }
        
        # Resend email using NotificationService
        service = NotificationService()
        result = service.send_email(
            user=user,
            template_name=template_name,
            context=context,
            category=category
        )
        
        if result:
            return JsonResponse({
                'success': True,
                'message': f'Email retry initiated for {email_log.to_email}',
                'status': 'sent'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Failed to send email. Check logs for details.'
            }, status=500)
    
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error retrying email {email_id}: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'Failed to retry email: {str(e)}'
        }, status=500)


@staff_member_required
def admin_sms_logs(request):
    """Admin view for SMS logs"""
    
    # Start with base queryset
    sms_logs = SMSLog.objects.all().order_by('-created_at')
    
    # Apply filters BEFORE pagination
    status = request.GET.get('status')
    if status:
        sms_logs = sms_logs.filter(status=status)
    
    to_phone = request.GET.get('to_phone')
    if to_phone:
        sms_logs = sms_logs.filter(to_phone__icontains=to_phone)
    
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if date_from:
        sms_logs = sms_logs.filter(created_at__gte=date_from)
    if date_to:
        sms_logs = sms_logs.filter(created_at__lte=date_to)
    
    # Search
    search_query = request.GET.get('q')
    if search_query:
        sms_logs = sms_logs.filter(
            Q(message__icontains=search_query) |
            Q(to_phone__icontains=search_query) |
            Q(to_name__icontains=search_query)
        )
    
    # Get statistics BEFORE pagination
    stats = {
        'total': sms_logs.count(),
        'sent': sms_logs.filter(status='sent').count(),
        'failed': sms_logs.filter(status='failed').count(),
        'delivered': sms_logs.filter(status='delivered').count(),
    }
    
    # Pagination - AFTER all filters
    paginator = Paginator(sms_logs, 50)
    page = request.GET.get('page')
    
    try:
        sms_logs_page = paginator.page(page)
    except PageNotAnInteger:
        sms_logs_page = paginator.page(1)
    except EmptyPage:
        sms_logs_page = paginator.page(paginator.num_pages)
    
    context = {
        'sms_logs': sms_logs_page,  # Use paginated object
        'stats': stats,
        'status_choices': SMSLog.STATUS_CHOICES,
        'filter_params': request.GET,
    }
    
    return render(request, 'admin/notifications/sms_logs.html', context)


@staff_member_required
def admin_preferences_list(request):
    """Admin view for user notification preferences"""
    
    preferences = NotificationPreference.objects.all().select_related('user').order_by('-updated_at')
    
    # Filters
    email_opt_in = request.GET.get('email_opt_in')
    if email_opt_in == 'true':
        preferences = preferences.filter(
            Q(email_order_updates=True) |
            Q(email_payment_updates=True) |
            Q(email_shipping_updates=True) |
            Q(email_promotions=True) |
            Q(email_account_updates=True)
        )
    elif email_opt_in == 'false':
        preferences = preferences.filter(
            email_order_updates=False,
            email_payment_updates=False,
            email_shipping_updates=False,
            email_promotions=False,
            email_account_updates=False
        )
    
    sms_opt_in = request.GET.get('sms_opt_in')
    if sms_opt_in == 'true':
        preferences = preferences.filter(
            Q(sms_order_updates=True) |
            Q(sms_payment_updates=True) |
            Q(sms_shipping_updates=True) |
            Q(sms_promotions=True)
        )
    elif sms_opt_in == 'false':
        preferences = preferences.filter(
            sms_order_updates=False,
            sms_payment_updates=False,
            sms_shipping_updates=False,
            sms_promotions=False
        )
    
    do_not_disturb = request.GET.get('do_not_disturb')
    if do_not_disturb == 'true':
        preferences = preferences.filter(do_not_disturb=True)
    elif do_not_disturb == 'false':
        preferences = preferences.filter(do_not_disturb=False)
    
    # Search
    search_query = request.GET.get('q')
    if search_query:
        preferences = preferences.filter(
            Q(user__username__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query)
        )
    
    # Statistics (compute BEFORE pagination to use QuerySet.filter())
    stats = {
        'total': preferences.count(),
        'do_not_disturb': preferences.filter(do_not_disturb=True).count(),
        'email_opt_in': preferences.filter(
            Q(email_order_updates=True) |
            Q(email_payment_updates=True) |
            Q(email_shipping_updates=True) |
            Q(email_promotions=True) |
            Q(email_account_updates=True)
        ).count(),
        'sms_opt_in': preferences.filter(
            Q(sms_order_updates=True) |
            Q(sms_payment_updates=True) |
            Q(sms_shipping_updates=True) |
            Q(sms_promotions=True)
        ).count(),
    }
    
    # Pagination (after stats)
    paginator = Paginator(preferences, 50)
    page = request.GET.get('page')
    
    try:
        preferences = paginator.page(page)
    except PageNotAnInteger:
        preferences = paginator.page(1)
    except EmptyPage:
        preferences = paginator.page(paginator.num_pages)
    
    context = {
        'preferences': preferences,
        'stats': stats,
        'filter_params': request.GET,
    }
    
    return render(request, 'admin/notifications/preferences_list.html', context)

logger = logging.getLogger(__name__)

@staff_member_required
def admin_send_bulk_notification(request):
    """Admin view for sending bulk notifications"""
    
    if request.method == 'POST':
        try:
            # Get form data
            notification_type = request.POST.get('notification_type')
            category = request.POST.get('category')
            template_name = request.POST.get('template_name')
            subject = request.POST.get('subject')
            message = request.POST.get('message')
            user_ids = request.POST.getlist('user_ids')
            send_to_all = request.POST.get('send_to_all') == 'on'
            
            # Get users (exclude admin/staff users)
            if send_to_all:
                users = User.objects.filter(is_active=True).exclude(is_staff=True)
            elif user_ids:
                users = User.objects.filter(id__in=user_ids, is_active=True).exclude(is_staff=True)
            else:
                messages.error(request, 'Please select users to send notifications to.')
                return redirect('notifications:admin_send_bulk_notification')
            
            # Create context
            context = {
                'site_name': getattr(settings, 'SITE_NAME', 'TechStore'),
                'site_url': getattr(settings, 'SITE_URL', 'https://techstore.com'),
                'current_year': timezone.now().year,
                'custom_message': message,
            }
            
            # Send notifications
            notification_service = NotificationService()
            results = {
                'total': users.count(),
                'success': 0,
                'failed': 0,
            }
            
            for user in users:
                try:
                    success = False
                    
                    if notification_type == 'email':
                        success = notification_service.send_email(
                            user=user,
                            template_name=template_name,
                            context=context,
                            category=category,
                        )
                    elif notification_type == 'sms':
                        success = notification_service.send_sms(
                            user=user,
                            template_name=template_name,
                            context=context,
                            category=category,
                        )
                    elif notification_type == 'push':
                        success = notification_service.send_push(
                            user=user,
                            template_name=template_name,
                            context=context,
                            category=category,
                        )
                    
                    if success:
                        results['success'] += 1
                    else:
                        results['failed'] += 1
                
                except Exception as e:
                    # Log the error
                    logger.error(f"Error sending notification to {user.username}: {str(e)}", exc_info=True)
                    results['failed'] += 1
            
            messages.success(request, f"Bulk notification sent: {results['success']} successful, {results['failed']} failed.")
            
        except Exception as e:
            # Log the error
            logger.error(f"Error in bulk notification: {str(e)}", exc_info=True)
            messages.error(request, f"Error sending bulk notification: {str(e)}")
    
    # Get available templates
    templates = NotificationTemplate.objects.filter(is_active=True)
    
    context = {
        'templates': templates,
        'notification_types': Notification.NOTIFICATION_TYPE_CHOICES,
        'categories': NotificationTemplate.NOTIFICATION_CATEGORY_CHOICES,
    }
    
    return render(request, 'admin/notifications/send_bulk_notification.html', context)



@staff_member_required
def admin_test_notification(request):
    """Admin view for testing notifications"""
    
    users = User.objects.all().order_by('-date_joined')[:20]
    templates = NotificationTemplate.objects.filter(is_active=True)
    
    # Check system configuration status
    email_configured = bool(getattr(settings, 'EMAIL_BACKEND', None))
    sms_configured = bool(getattr(settings, 'TWILIO_ACCOUNT_SID', None))
    push_configured = bool(getattr(settings, 'FIREBASE_CREDENTIALS', None))
    
    # Get recent test notifications
    recent_notifications = Notification.objects.filter(
        data__test=True
    ).select_related('user', 'template').order_by('-created_at')[:10]
    
    if request.method == 'POST':
        try:
            user_id = request.POST.get('user_id')
            notification_type = request.POST.get('notification_type')
            template_id = request.POST.get('template_id')
            test_data = request.POST.get('test_data', '{}')
            
            # Validate inputs
            if not all([user_id, notification_type, template_id]):
                messages.error(request, 'All fields are required.')
                return redirect('notifications:admin_test_notification')
            
            # Get user and template
            user = get_object_or_404(User, pk=user_id)
            template = get_object_or_404(NotificationTemplate, pk=template_id)
            
            # Parse test data
            try:
                test_context = json.loads(test_data)
            except json.JSONDecodeError:
                messages.error(request, 'Invalid JSON format in test data.')
                return redirect('notifications:admin_test_notification')
            
            # Add standard context
            test_context.update({
                'user': user,
                'test': True,
                'timestamp': timezone.now(),
                'site_name': getattr(settings, 'SITE_NAME', 'TechStore'),
                'site_url': getattr(settings, 'SITE_URL', 'https://techstore.com'),
                'current_year': timezone.now().year,
            })
            
            # Send notification
            notification_service = NotificationService()
            
            if notification_type == 'email':
                success = notification_service.send_email(
                    user=user,
                    template_name=template.name,
                    context=test_context,
                    category=template.category,
                )
            elif notification_type == 'sms':
                success = notification_service.send_sms(
                    user=user,
                    template_name=template.name,
                    context=test_context,
                    category=template.category,
                )
            elif notification_type == 'push':
                success = notification_service.send_push(
                    user=user,
                    template_name=template.name,
                    context=test_context,
                    category=template.category,
                )
            elif notification_type == 'in_app':
                # Create in-app notification directly
                Notification.objects.create(
                    user=user,
                    notification_type='in_app',
                    template=template,
                    title=template.subject,
                    message=template.text_content or template.html_content,
                    data={'test': True, **test_context},
                    status='sent',
                )
                success = True
            else:
                messages.error(request, 'Invalid notification type.')
                return redirect('notifications:admin_test_notification')
            
            if success:
                messages.success(request, f'Test {notification_type} notification sent to {user.get_full_name or user.username}!')
            else:
                messages.warning(request, f'Test {notification_type} notification was processed but may not have been delivered.')
            
            return redirect('notifications:admin_test_notification')
        
        except Exception as e:
            logger.error(f"Error in test notification: {str(e)}", exc_info=True)
            messages.error(request, f'Error sending test notification: {str(e)}')
            return redirect('notifications:admin_test_notification')
    
    context = {
        'users': users,
        'templates': templates,
        'recent_notifications': recent_notifications,
        'email_configured': email_configured,
        'sms_configured': sms_configured,
        'push_configured': push_configured,
    }
    
    return render(request, 'admin/notifications/test_notifications.html', context)


@staff_member_required
def admin_quick_test(request):
    """Quick test notifications endpoint"""
    
    if request.method == 'POST':
        try:
            user_id = request.POST.get('user_id')
            test_type = request.POST.get('test_type')
            
            if not user_id or not test_type:
                messages.error(request, 'User and test type are required.')
                return redirect('notifications:admin_test_notification')
            
            user = get_object_or_404(User, pk=user_id)
            
            # Create test context
            test_context = {
                'user': user,
                'test': True,
                'timestamp': timezone.now(),
                'site_name': getattr(settings, 'SITE_NAME', 'TechStore'),
                'site_url': getattr(settings, 'SITE_URL', 'https://techstore.com'),
                'current_year': timezone.now().year,
            }
            
            # Get or create test template
            template, created = NotificationTemplate.objects.get_or_create(
                name='test_notification',
                template_type=test_type,
                defaults={
                    'category': 'system',
                    'subject': f'Test {test_type.upper()} Notification',
                    'html_content': f'<h2>Test {test_type.upper()} Notification</h2><p>This is a test notification sent at {{ timestamp|date:"Y-m-d H:i:s" }}</p>',
                    'text_content': f'Test {test_type.upper()} Notification - Sent at {{ timestamp|date:"Y-m-d H:i:s" }}',
                    'push_content': f'Test {test_type.upper()} - Sent at {{ timestamp|date:"Y-m-d H:i:s" }}',
                    'is_active': True,
                }
            )
            
            # Send notification
            notification_service = NotificationService()
            
            if test_type == 'email':
                success = notification_service.send_email(
                    user=user,
                    template_name='test_notification',
                    context=test_context,
                )
            elif test_type == 'sms':
                success = notification_service.send_sms(
                    user=user,
                    template_name='test_notification',
                    context=test_context,
                )
            elif test_type == 'push':
                success = notification_service.send_push(
                    user=user,
                    template_name='test_notification',
                    context=test_context,
                )
            elif test_type == 'in_app':
                Notification.objects.create(
                    user=user,
                    notification_type='in_app',
                    template=template,
                    title='Test Notification',
                    message=f'Test in-app notification sent at {timezone.now()}',
                    data={'test': True},
                    status='sent',
                )
                success = True
            
            if success:
                messages.success(request, f'✓ Test {test_type} notification sent successfully to {user.get_full_name or user.username}!')
            else:
                messages.warning(request, f'Test {test_type} notification was processed.')
        
        except Exception as e:
            logger.error(f"Error in quick test: {str(e)}", exc_info=True)
            messages.error(request, f'Error: {str(e)}')
    
    return redirect('notifications:admin_test_notification')