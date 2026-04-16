from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.crypto import get_random_string
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django_ratelimit.decorators import ratelimit
from urllib.parse import urlparse
import jwt
from datetime import datetime, timedelta

from .models import User
from .forms import RegistrationForm, LoginForm, ProfileForm
from orders.models import Order
from products.models import Wishlist

def is_safe_redirect_url(url, allowed_hosts=None):
    """
    Check if URL is safe for redirect (prevent open redirect attacks)
    """
    if not url:
        return False
    
    # Must start with / (relative URL)
    if not url.startswith('/'):
        return False
    
    # Cannot start with //
    if url.startswith('//'):
        return False
    
    # Parse the URL
    parsed = urlparse(url)
    
    # Must not have a netloc (domain)
    if parsed.netloc:
        return False
    
    return True

@ratelimit(key='ip', rate='10/m')
def register_view(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password1'])
            user.role = form.cleaned_data.get('role', 'customer')  # Save role
            user.save()
            
            # Send verification email
            send_verification_email(user)
            
            messages.success(request, 'Registration successful! Please check your email to verify your account.')
            return redirect('users:login')
    else:
        form = RegistrationForm()
    
    return render(request, 'users/register.html', {'form': form})

@ratelimit(key='ip', rate='10/m')
def login_view(request):
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            
            if user is not None:
                if user.email_verified:
                    login(request, user)
                    messages.success(request, 'You have been logged in successfully.')
                    next_url = request.POST.get('next') or request.GET.get('next')
                    if next_url and is_safe_redirect_url(next_url):
                        return redirect(next_url)
                    return redirect('home')
                else:
                    messages.error(request, 'Please verify your email before logging in.')
            else:
                messages.error(request, 'Invalid username or password.')
    else:
        form = LoginForm()
    
    # Pass next parameter to template
    next_url = request.GET.get('next', '')
    context = {'form': form, 'next': next_url}
    return render(request, 'users/login.html', context)

def logout_view(request):
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('home')

# users/views.py - Update profile_view
@login_required
def profile_view(request):
    """User dashboard with stats"""
    
    # Get user orders
    orders = Order.objects.filter(user=request.user)
    
    # Get wishlist count
    wishlist_count = Wishlist.objects.filter(user=request.user).count()
    
    # Prepare context with order_number fallback
    recent_orders = []
    for order in orders.order_by('-created_at')[:5]:
        recent_orders.append({
            'id': order.id,
            'order_number': getattr(order, 'order_number', f"ORD-{order.id:06d}"),
            'created_at': order.created_at,
            'total_amount': order.total_amount,
            'status': order.status,
            'items_count': order.items.count() if hasattr(order, 'items') else 0,
        })
    
    context = {
        'user': request.user,
        'order_count': orders.count(),
        'completed_orders': orders.filter(status='delivered').count(),
        'pending_orders': orders.filter(status__in=['pending', 'processing']).count(),
        'wishlist_count': wishlist_count,
        'recent_orders': recent_orders,
    }
    
    return render(request, 'users/dashboard.html', context)

# users/views.py - Update profile_edit view
@login_required
def profile_edit(request):
    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            # Handle profile picture removal
            if request.POST.get('remove_picture'):
                if request.user.profile_picture:
                    request.user.profile_picture.delete(save=False)
            
            form.save()
            messages.success(request, 'Profile updated successfully.')
            return redirect('users:profile')
    else:
        form = ProfileForm(instance=request.user)
    
    return render(request, 'users/profile_edit.html', {'form': form})

@login_required
def password_change(request):
    if request.method == 'POST':
        old_password = request.POST.get('old_password')
        new_password1 = request.POST.get('new_password1')
        new_password2 = request.POST.get('new_password2')
        
        if not request.user.check_password(old_password):
            messages.error(request, 'Old password is incorrect.')
        elif new_password1 != new_password2:
            messages.error(request, 'New passwords do not match.')
        elif len(new_password1) < 8:
            messages.error(request, 'Password must be at least 8 characters long.')
        else:
            request.user.set_password(new_password1)
            request.user.save()
            
            # Re-authenticate user after password change
            user = authenticate(username=request.user.username, password=new_password1)
            if user:
                login(request, user)
            
            messages.success(request, 'Password changed successfully.')
            return redirect('users:profile')
    
    return render(request, 'users/password_change.html')

def send_verification_email(user):
    """Send email verification link - URL-safe version"""
    # Create token with timestamp
    import time
    import hashlib
    
    # Create a simple hash token
    token_string = f"{user.id}:{user.email}:{time.time()}"
    token_hash = hashlib.sha256(token_string.encode()).hexdigest()
    
    # Store in user model (add a field for this)
    user.email_verification_token = token_hash
    user.email_token_created = timezone.now()
    user.save()
    
    verification_url = f"{settings.SITE_URL}/users/verify-email/{token_hash}/"
    
    # Send email with formatted body
    subject = 'Email Verification - E-Commerce Store'
    message = f'''Email Verification
Hello {user.first_name or user.username},

Thank you for registering with E-Commerce Store!

To complete your registration and verify your email address, please click the button below:

Verify Email Address

Or copy and paste this link in your browser:

{verification_url}

This link will expire in 24 hours.

If you did not create this account, please ignore this email.

© 2024 E-Commerce Store. All rights reserved.

This is an automated email, please do not reply to this message.
'''
    
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email])

def verify_email(request, token):
    """Verify user email - URL-safe version"""
    try:
        # Find user by token
        user = User.objects.get(email_verification_token=token)
        
        # Check if token is older than 24 hours
        if user.email_token_created < timezone.now() - timedelta(hours=24):
            messages.error(request, 'Verification link has expired.')
        else:
            user.email_verified = True
            user.email_verification_token = ''  # Clear token
            user.save()
            messages.success(request, 'Email verified successfully! You can now log in.')
            
    except User.DoesNotExist:
        messages.error(request, 'Invalid verification link.')
    
    return redirect('users:login')

@login_required
def resend_verification(request):
    """Resend verification email"""
    if not request.user.email_verified:
        send_verification_email(request.user)
        messages.success(request, 'Verification email sent. Please check your inbox.')
    else:
        messages.info(request, 'Your email is already verified.')
    
    return redirect('users:profile')

def forgot_password(request):
    """Custom forgot password view"""
    if request.method == 'POST':
        email = request.POST.get('email')
        try:
            user = User.objects.get(email=email)
            
            # Generate reset token
            token = jwt.encode(
                {
                    'user_id': user.id,
                    'exp': timezone.now() + timedelta(hours=1)
                },
                settings.SECRET_KEY,
                algorithm='HS256'
            )
            
            # Send reset email
            reset_url = f"{settings.SITE_URL}/users/reset-password/{token}/"
            
            subject = 'Reset Your Password'
            message = f'''
            Hi {user.username},
            
            You requested to reset your password. Click the link below:
            
            {reset_url}
            
            This link will expire in 1 hour.
            
            If you didn't request this, please ignore this email.
            
            Best regards,
            TechStore Team
            '''
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False,
            )
            
            messages.success(request, 'Password reset instructions sent to your email.')
            return redirect('users:login')
        
        except User.DoesNotExist:
            messages.error(request, 'No account found with this email address.')
    
    return render(request, 'users/forgot_password.html')

def reset_password(request, token):
    """Custom reset password view"""
    
    # Verify token
    valid_token = False
    user_id = None
    
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        user_id = payload['user_id']
        valid_token = True
    except (jwt.ExpiredSignatureError, jwt.DecodeError):
        valid_token = False
    
    if request.method == 'POST' and valid_token:
        new_password1 = request.POST.get('new_password1')
        new_password2 = request.POST.get('new_password2')
        
        if new_password1 != new_password2:
            messages.error(request, 'Passwords do not match.')
        elif len(new_password1) < 8:
            messages.error(request, 'Password must be at least 8 characters long.')
        else:
            try:
                user = User.objects.get(id=user_id)
                user.set_password(new_password1)
                user.save()
                
                messages.success(request, 'Password reset successfully. You can now log in.')
                return redirect('users:login')
            except User.DoesNotExist:
                messages.error(request, 'Invalid reset token.')
    
    context = {
        'valid_token': valid_token,
        'token': token,
    }
    
    return render(request, 'users/password_reset.html', context)

from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q, Count, Sum
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.generic import ListView, DetailView, UpdateView, DeleteView, CreateView
from django.urls import reverse_lazy
from django.shortcuts import redirect
from .models import User
from .forms import AdminUserForm

# Add these imports at the top if not already present
from django.contrib.auth.decorators import login_required, user_passes_test

def is_admin_user(user):
    """Check if user is admin or staff."""
    return user.is_staff or user.is_superuser or user.role in ['admin', 'seller']

# Decorator for admin-only views
def admin_required(view_func):
    decorated_view_func = login_required(
        user_passes_test(is_admin_user, login_url='login')(view_func)
    )
    return decorated_view_func

@admin_required
def admin_user_list(request):
    """Admin view for listing users."""
    # Get filter parameters
    role_filter = request.GET.get('role', '')
    status_filter = request.GET.get('status', '')
    search_query = request.GET.get('q', '')
    verified_filter = request.GET.get('verified', '')
    
    # Start with all users
    users = User.objects.all().order_by('-date_joined')
    
    # Apply filters
    if role_filter:
        users = users.filter(role=role_filter)
    
    if status_filter == 'active':
        users = users.filter(is_active=True)
    elif status_filter == 'inactive':
        users = users.filter(is_active=False)
    
    if verified_filter == 'verified':
        users = users.filter(email_verified=True, phone_verified=True)
    elif verified_filter == 'email_only':
        users = users.filter(email_verified=True, phone_verified=False)
    elif verified_filter == 'phone_only':
        users = users.filter(email_verified=False, phone_verified=True)
    elif verified_filter == 'unverified':
        users = users.filter(email_verified=False, phone_verified=False)
    
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(phone__icontains=search_query)
        )
    
    # Pagination
    page = request.GET.get('page', 1)
    paginator = Paginator(users, 25)  # Show 25 users per page
    
    try:
        users_page = paginator.page(page)
    except PageNotAnInteger:
        users_page = paginator.page(1)
    except EmptyPage:
        users_page = paginator.page(paginator.num_pages)
    
    # Calculate stats
    user_stats = {
        'total_users': User.objects.count(),
        'active_users': User.objects.filter(is_active=True).count(),
        'customers': User.objects.filter(role='customer').count(),
        'sellers': User.objects.filter(role='seller').count(),
        'admins': User.objects.filter(role='admin').count(),
        'verified_users': User.objects.filter(email_verified=True).count(),
        'new_today': User.objects.filter(
            date_joined__date=timezone.now().date()
        ).count(),
        # Add this calculation
        'unverified_users': User.objects.filter(email_verified=False).count(),
    }
    
    context = {
        'users': users_page,
        'user_stats': user_stats,
        'role_filter': role_filter,
        'status_filter': status_filter,
        'verified_filter': verified_filter,
        'search_query': search_query,
        'role_choices': User.ROLE_CHOICES,
        'pending_users': User.objects.filter(is_active=False).count(),
    }
    
    return render(request, 'admin/users/user_list.html', context)

@admin_required
def admin_user_detail(request, pk):
    """Admin view for user details."""
    user = get_object_or_404(User, pk=pk)
    
    # Get user orders
    orders = Order.objects.filter(user=user).order_by('-created_at')[:10]
    
    # Get user wishlist
    wishlist_items = Wishlist.objects.filter(user=user).select_related('product')[:10]
    
    # Calculate user stats
    order_stats = {
        'total_orders': Order.objects.filter(user=user).count(),
        'total_spent': Order.objects.filter(
            user=user, 
            payment_status='paid'
        ).aggregate(total=Sum('total_amount'))['total'] or 0,
        'last_order': Order.objects.filter(user=user).order_by('-created_at').first(),
    }
    
    context = {
        'user_obj': user,  # Using 'user_obj' to avoid conflict with request.user
        'orders': orders,
        'wishlist_items': wishlist_items,
        'order_stats': order_stats,
    }
    
    return render(request, 'admin/users/user_detail.html', context)

@admin_required
def admin_user_create(request):
    """Admin view for creating a new user."""
    if request.method == 'POST':
        form = AdminUserForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save(commit=False)
            
            # Handle password
            if form.cleaned_data['password']:
                user.set_password(form.cleaned_data['password'])
            else:
                # Generate random password
                import secrets
                password = secrets.token_urlsafe(12)
                user.set_password(password)
            
            # Set email verified if needed
            if form.cleaned_data.get('auto_verify_email'):
                user.email_verified = True
            
            user.save()
            form.save_m2m()  # Save many-to-many relationships
            
            messages.success(request, f'User {user.username} created successfully.')
            
            # Send welcome email if requested
            if form.cleaned_data.get('send_welcome_email'):
                send_welcome_email(user, form.cleaned_data['password'])
            
            return redirect('users:admin_user_list')
    else:
        form = AdminUserForm()
    
    context = {
        'form': form,
        'title': 'Create New User',
    }
    
    return render(request, 'admin/users/user_form.html', context)

@admin_required
def admin_user_edit(request, pk):
    """Admin view for editing a user."""
    user = get_object_or_404(User, pk=pk)
    
    if request.method == 'POST':
        form = AdminUserForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            user = form.save()
            
            # Handle password change
            new_password = form.cleaned_data.get('password')
            if new_password:
                user.set_password(new_password)
                user.save()
            
            messages.success(request, f'User {user.username} updated successfully.')
            return redirect('users:admin_user_detail', pk=user.pk)
    else:
        form = AdminUserForm(instance=user)
    
    context = {
        'form': form,
        'user_obj': user,
        'title': f'Edit User: {user.username}',
    }
    
    return render(request, 'admin/users/user_form.html', context)

@admin_required
def admin_user_delete(request, pk):
    """Admin view for deleting a user."""
    user = get_object_or_404(User, pk=pk)
    
    if request.method == 'POST':
        username = user.username
        user.delete()
        messages.success(request, f'User {username} deleted successfully.')
        return redirect('users:admin_user_list')
    
    context = {
        'user_obj': user,
    }
    
    return render(request, 'admin/users/user_confirm_delete.html', context)

@admin_required
def admin_user_analytics(request):
    """User analytics dashboard."""
    from django.db.models.functions import TruncMonth, TruncWeek, TruncDay
    
    # Time period filter
    period = request.GET.get('period', 'month')  # day, week, month, year
    
    # Date range
    end_date = timezone.now()
    if period == 'day':
        start_date = end_date - timedelta(days=1)
        trunc_func = TruncDay
        group_by = 'day'
    elif period == 'week':
        start_date = end_date - timedelta(weeks=4)
        trunc_func = TruncWeek
        group_by = 'week'
    elif period == 'month':
        start_date = end_date - timedelta(days=90)  # 3 months
        trunc_func = TruncMonth
        group_by = 'month'
    else:  # year
        start_date = end_date - timedelta(days=365)
        trunc_func = TruncMonth
        group_by = 'month'
    
    # User registration trends
    registrations_qs = (
        User.objects
        .filter(date_joined__range=[start_date, end_date])
        .annotate(period=trunc_func('date_joined'))
        .values('period')
        .annotate(count=Count('id'))
        .order_by('period')
    )
    registrations = list(registrations_qs)  # Convert to list for template
    
    # Debug: Log if no data
    if not registrations:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f'No registration data for period: {period}, date range: {start_date} to {end_date}')
    
    # Role distribution
    role_distribution_qs = (
        User.objects
        .values('role')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    role_distribution = list(role_distribution_qs)  # Convert to list for template
    
    # User activity
    active_users = User.objects.filter(
        last_login__gte=end_date - timedelta(days=30)
    ).count()
    
    # Top customers by spending
    top_customers = []
    for user in User.objects.filter(role='customer'):
        total_spent = Order.objects.filter(
            user=user,
            payment_status='paid'
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        
        order_count = Order.objects.filter(user=user).count()
        
        if total_spent > 0:
            # Calculate average order value
            avg_order_value = total_spent / order_count if order_count > 0 else 0
            
            top_customers.append({
                'user': user,
                'total_spent': total_spent,
                'order_count': order_count,
                'avg_order_value': avg_order_value  # Add this
            })
    
    top_customers = sorted(top_customers, key=lambda x: x['total_spent'], reverse=True)[:10]
    
    # Geographic distribution
    location_stats = (
        User.objects
        .exclude(country='')
        .values('country')
        .annotate(count=Count('id'))
        .order_by('-count')[:10]
    )
    
    context = {
        'period': period,
        'registrations': list(registrations),
        'role_distribution': list(role_distribution),
        'active_users': active_users,
        'top_customers': top_customers,
        'location_stats': list(location_stats),
        'total_users': User.objects.count(),
        'new_users_today': User.objects.filter(
            date_joined__date=timezone.now().date()
        ).count(),
        'verified_users': User.objects.filter(email_verified=True).count(),
    }
    
    return render(request, 'admin/users/user_analytics.html', context)

@admin_required
def admin_user_bulk_actions(request):
    """Handle bulk actions for users."""
    if request.method == 'POST':
        action = request.POST.get('action')
        user_ids = request.POST.getlist('selected_users')
        
        if not user_ids:
            messages.error(request, 'No users selected.')
            return redirect('users:admin_user_list')
        
        users = User.objects.filter(id__in=user_ids)
        
        if action == 'activate':
            users.update(is_active=True)
            messages.success(request, f'{users.count()} users activated.')
        
        elif action == 'deactivate':
            users.update(is_active=False)
            messages.success(request, f'{users.count()} users deactivated.')
        
        elif action == 'verify_email':
            users.update(email_verified=True)
            messages.success(request, f'{users.count()} users email verified.')
        
        elif action == 'send_welcome':
            for user in users:
                send_welcome_email(user)
            messages.success(request, f'Welcome emails sent to {users.count()} users.')
        
        elif action == 'delete':
            count = users.count()
            users.delete()
            messages.success(request, f'{count} users deleted.')
        
        elif action == 'export_csv':
            return export_users_csv(users)
    
    return redirect('users:admin_user_list')

@admin_required
def admin_user_export(request):
    """Export users to CSV."""
    users = User.objects.all()
    return export_users_csv(users)

def export_users_csv(users):
    """Helper function to export users to CSV."""
    import csv
    from django.http import HttpResponse
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="users_export.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Username', 'Email', 'First Name', 'Last Name', 'Role',
        'Phone', 'Email Verified', 'Phone Verified', 'Active',
        'Date Joined', 'Last Login', 'Country'
    ])
    
    for user in users:
        writer.writerow([
            user.username,
            user.email,
            user.first_name,
            user.last_name,
            user.role,
            user.phone,
            'Yes' if user.email_verified else 'No',
            'Yes' if user.phone_verified else 'No',
            'Yes' if user.is_active else 'No',
            user.date_joined.strftime('%Y-%m-%d %H:%M:%S'),
            user.last_login.strftime('%Y-%m-%d %H:%M:%S') if user.last_login else '',
            user.country
        ])
    
    return response

# ============================ ADMIN PROFILE VIEWS ============================

@login_required
@admin_required
def admin_profile(request):
    """Admin profile dashboard - different from customer profile."""
    from orders.models import Order
    from django.db.models import Count, Sum
    from notifications.models import Notification
    
    # Check if user is admin
    if not (request.user.is_staff or request.user.role in ['admin', 'seller']):
        messages.error(request, 'Unauthorized access.')
        return redirect('products:home')
    
    # Get admin-specific statistics
    total_users = User.objects.count()
    total_orders = Order.objects.count()
    total_revenue = Order.objects.filter(payment_status='paid').aggregate(
        total=Sum('total_amount')
    )['total'] or 0
    
    # Recent activity
    recent_orders = Order.objects.select_related('user').order_by('-created_at')[:10]
    recent_users = User.objects.order_by('-date_joined')[:5]
    
    # Admin role statistics
    admin_count = User.objects.filter(role='admin').count()
    seller_count = User.objects.filter(role='seller').count()
    customer_count = User.objects.filter(role='customer').count()
    
    context = {
        'admin_user': request.user,
        'total_users': total_users,
        'total_orders': total_orders,
        'total_revenue': total_revenue,
        'admin_count': admin_count,
        'seller_count': seller_count,
        'customer_count': customer_count,
        'recent_orders': recent_orders,
        'recent_users': recent_users,
        'role': request.user.role,
        'is_superuser': request.user.is_superuser,
        'is_staff': request.user.is_staff,
    }
    
    return render(request, 'admin/users/admin_profile.html', context)

@login_required
@admin_required
def admin_profile_edit(request):
    """Edit admin profile - different form/interface from customer profile."""
    # Check if user is admin
    if not (request.user.is_staff or request.user.role in ['admin', 'seller']):
        messages.error(request, 'Unauthorized access.')
        return redirect('home')
    
    if request.method == 'POST':
        # Handle admin profile update
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        email = request.POST.get('email', '')
        phone = request.POST.get('phone', '')
        
        # Check if email already exists (for other users)
        if email != request.user.email:
            if User.objects.filter(email=email).exclude(id=request.user.id).exists():
                messages.error(request, 'Email already in use.')
                return redirect('users:admin_profile_edit')
        
        # Update user
        request.user.first_name = first_name
        request.user.last_name = last_name
        request.user.email = email
        request.user.phone = phone
        
        # Handle profile picture
        if 'profile_picture' in request.FILES:
            request.user.profile_picture = request.FILES['profile_picture']
        
        request.user.save()
        messages.success(request, 'Admin profile updated successfully.')
        return redirect('users:admin_profile')
    
    context = {
        'admin_user': request.user,
        'role': request.user.role,
    }
    
    return render(request, 'admin/users/admin_profile_edit.html', context)

def send_welcome_email(user, password=None):
    """Send welcome email to user."""
    subject = 'Welcome to TechStore!'
    
    message = f'''
    Hi {user.first_name or user.username},
    
    Welcome to TechStore! Your account has been created successfully.
    
    Account Details:
    - Username: {user.username}
    - Email: {user.email}
    '''
    
    if password:
        message += f'- Password: {password}\n\n'
        message += 'Please change your password after first login.'
    
    message += '''
    
    You can now:
    - Browse our products
    - Place orders
    - Track your shipments
    - Manage your profile
    
    If you have any questions, please contact our support team.
    
    Best regards,
    TechStore Team
    '''
    
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )