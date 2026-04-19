from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import timedelta, datetime
from django.core.paginator import Paginator
from django_ratelimit.decorators import ratelimit
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from io import BytesIO
import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.db.models import Prefetch
from .models import Order, OrderItem, ReturnRequest
from users.models import User
import json
from .models import Order, OrderItem, ReturnRequest, Invoice
from cart.models import Cart
from payments.models import Payment
from .services import send_order_confirmation_email, send_order_status_update_email, send_payment_status_update_email

# orders/views.py - Update order_list view
from django.db.models import Count

# orders/views.py - Update with simple payment bypass
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import timedelta, datetime
from django.core.paginator import Paginator
from django_ratelimit.decorators import ratelimit
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from io import BytesIO
import json
import uuid
from decimal import Decimal
from .models import Order, OrderItem, ReturnRequest, Invoice
from cart.models import Cart
from payments.models import Payment

def is_admin_or_staff(user):
    """Check if user is admin or staff"""
    return user.is_authenticated and (user.is_staff or user.is_superuser or getattr(user, 'role', '') == 'admin')

def recalculate_order_totals(order):
    """
    Recalculate order totals based on order items to ensure correlation.
    This ensures total price (sum of items) always matches order total.
    """
    # Recalculate subtotal from order items
    items_total = order.items.aggregate(total=Sum('total_price'))['total'] or Decimal('0')
    items_total = Decimal(str(items_total)).quantize(Decimal('0.01'))
    
    # Recalculate tax (10% of subtotal, not shipping)
    tax = (items_total * Decimal('0.1')).quantize(Decimal('0.01'))
    
    # Get shipping cost
    shipping = Decimal(str(order.shipping_cost)).quantize(Decimal('0.01'))
    
    # Get discount
    discount = Decimal(str(order.discount_amount)).quantize(Decimal('0.01'))
    
    # Calculate final total: items + shipping + tax - discount
    total = (items_total + shipping + tax - discount).quantize(Decimal('0.01'))
    
    # Update order if values differ
    if order.subtotal != items_total or order.tax_amount != tax or order.total_amount != total:
        order.subtotal = items_total
        order.tax_amount = tax
        order.total_amount = total
        order.save()
        return True  # Updated
    
    return False  # No changes needed

@login_required
def checkout(request):
    """Checkout view with bypass payment options"""
    try:
        # Get or create cart for logged-in user
        cart, created = Cart.objects.get_or_create(user=request.user, is_active=True)
        cart_items = cart.items.select_related('product').all()
        
        if not cart_items:
            messages.error(request, 'Your cart is empty. Please add items before checkout.')
            return redirect('products:product_list')
        
        # Check stock availability
        for item in cart_items:
            if item.quantity > item.product.stock:
                messages.error(request, f'Only {item.product.stock} of {item.product.name} available.')
                return redirect('cart:cart')
        
        # Calculate totals using Decimal for consistency
        subtotal = Decimal(str(cart.total_price))
        shipping_cost = Decimal('0')
        if subtotal <= Decimal('50'):
            shipping_cost = Decimal('5.99')
        
        # FIX: Use Decimal for all calculations to ensure correlation
        tax = (subtotal * Decimal('0.1')).quantize(Decimal('0.01'))
        discount = Decimal('0')
        grand_total = (subtotal + shipping_cost + tax - discount).quantize(Decimal('0.01'))
        
        # Convert to float for template display, but keep Decimal for calculations
        context = {
            'cart': cart,
            'cart_items': cart_items,
            'cart_total': float(subtotal),
            'cart_tax': float(tax),
            'cart_discount': float(discount),
            'cart_grand_total': float(grand_total),
            'shipping_cost': float(shipping_cost),
            'subtotal_decimal': subtotal,  # Keep decimal for calculations
        }
        
        return render(request, 'orders/checkout.html', context)
    except Exception as e:
        messages.error(request, f'Error loading cart: {str(e)}')
        return redirect('products:product_list')
    
@login_required
def checkout_process(request):
    """Process checkout with bypass payment"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid request method'})
    
    try:
        cart = Cart.objects.get(user=request.user)
        cart_items = cart.items.select_related('product').all()
        
        if not cart_items:
            return JsonResponse({'success': False, 'message': 'Your cart is empty'})
        
        # Get form data
        payment_method = request.POST.get('payment_method', 'test')
        shipping_method = request.POST.get('shipping_method', 'standard')
        
        # Get shipping information
        shipping_data = {
            'first_name': request.POST.get('first_name'),
            'last_name': request.POST.get('last_name'),
            'email': request.POST.get('email'),
            'phone': request.POST.get('phone'),
            'address': request.POST.get('address'),
            'city': request.POST.get('city'),
            'state': request.POST.get('state'),
            'zip_code': request.POST.get('zip_code'),
            'country': request.POST.get('country'),
        }
        
        # Validate required fields
        required_fields = ['first_name', 'last_name', 'email', 'phone', 'address', 'city', 'state', 'zip_code', 'country']
        for field in required_fields:
            if not request.POST.get(field):
                return JsonResponse({'success': False, 'message': f'Please fill in all required fields'})
        
        # Calculate totals - FIX DECIMAL ISSUES
        subtotal = Decimal('0')
        
        # IMPORTANT: Get subtotal from cart items
        for item in cart_items:
            item_price = Decimal(str(item.total_price)) if item.total_price else Decimal('0')
            subtotal += item_price
        
        # Determine shipping based on subtotal
        shipping_cost = Decimal('0')
        if subtotal <= Decimal('50'):
            shipping_cost = Decimal('5.99')
        elif shipping_method == 'express':
            shipping_cost = Decimal('12.99')
        elif shipping_method == 'overnight':
            shipping_cost = Decimal('24.99')
        
        # Calculate tax based on subtotal (not including shipping)
        tax = (subtotal * Decimal('0.1')).quantize(Decimal('0.01'))  # 10% tax - ROUND TO 2 decimals
        discount = Decimal('0')
        
        # Calculate grand total: subtotal + shipping + tax - discount
        total_amount = (subtotal + shipping_cost + tax - discount).quantize(Decimal('0.01'))
        
        order_number = f"ORD-{uuid.uuid4().hex[:8].upper()}"
        
        # Create order
        order = Order.objects.create(
            user=request.user,
            order_number=order_number,
            subtotal=subtotal,
            shipping_cost=shipping_cost,
            tax_amount=tax,
            discount_amount=discount,
            total_amount=total_amount,
            
            # Payment info
            payment_method=payment_method,
            payment_status='paid' if payment_method == 'test' else 'pending',
            status='confirmed' if payment_method == 'test' else 'pending',
            
            # Shipping info
            shipping_address=shipping_data['address'],
            shipping_city=shipping_data['city'],
            shipping_state=shipping_data['state'],
            shipping_country=shipping_data['country'],
            shipping_zip_code=shipping_data['zip_code'],
            shipping_phone=shipping_data['phone'],
            
            # Billing info (same as shipping for now)
            billing_address=shipping_data['address'],
            billing_city=shipping_data['city'],
            billing_state=shipping_data['state'],
            billing_country=shipping_data['country'],
            billing_zip_code=shipping_data['zip_code'],
            
            # Mark as paid for test payments
            paid_at=timezone.now() if payment_method == 'test' else None,
        )
        
        # Create order items and update product stock
        items_subtotal = Decimal('0')
        for item in cart_items:
            # FIX: Use cart item price (discount_price or price), not product.price
            unit_price = Decimal(str(item.price))
            total_price = Decimal(str(item.total_price))
            
            order_item = OrderItem.objects.create(
                order=order,
                product=item.product,
                product_name=item.product.name,
                product_sku=item.product.sku,
                quantity=item.quantity,
                unit_price=unit_price,  # Use actual price from cart
                total_price=total_price,  # Use actual total from cart
                product_data={
                    'name': item.product.name,
                    'description': item.product.description,
                    'price': str(item.price),  # Store actual price paid
                    'category': item.product.category.name if item.product.category else 'Uncategorized',
                }
            )
            
            # Add to items subtotal
            items_subtotal += order_item.total_price
            
            # Update product stock
            item.product.stock -= item.quantity
            item.product.sold_count += item.quantity
            item.product.save()
        
        # IMPORTANT: Verify and recalculate totals based on actual order items
        items_subtotal = items_subtotal.quantize(Decimal('0.01'))
        recalculated_tax = (items_subtotal * Decimal('0.1')).quantize(Decimal('0.01'))
        recalculated_total = (items_subtotal + shipping_cost + recalculated_tax - discount).quantize(Decimal('0.01'))
        
        # Update order with verified totals to ensure correlation
        order.subtotal = items_subtotal
        order.tax_amount = recalculated_tax
        order.total_amount = recalculated_total
        order.save()
        
        # Clear cart
        cart.items.all().delete()
        
        # Create a simple payment record for test payments
        if payment_method == 'test':
            from payments.models import Payment
            Payment.objects.create(
                user=request.user,
                order=order,
                amount=order.total_amount,  # Use recalculated order total
                currency='USD',
                payment_method='test',
                payment_gateway='test',
                status='completed',
                is_successful=True,
                customer_email=shipping_data['email'],
                gateway_transaction_id=f"TEST-{uuid.uuid4().hex[:8].upper()}",
                paid_at=timezone.now(),
            )
        
        # Create invoice
        Invoice.objects.create(
            order=order,
            invoice_number=f"INV-{order_number}",
        )
        
        # Send confirmation email
        try:
            send_order_confirmation_email(order)
        except Exception as e:
            print(f"Warning: Could not send confirmation email - {str(e)}")
        
        return JsonResponse({
            'success': True,
            'order_id': order.order_number,
            'redirect_url': f'/orders/success/{order.order_number}/'
        })
        
    except Cart.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Your cart is empty'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})

def order_list(request):
    # Get user's orders
    orders = Order.objects.filter(user=request.user).order_by('-created_at')
    
    # Calculate statistics
    total_orders = orders.count()
    pending_count = orders.filter(status='pending').count()
    delivered_count = orders.filter(status='delivered').count()
    processing_count = orders.filter(status='processing').count()
    shipped_count = orders.filter(status='shipped').count()
    
    # Calculate percentages
    pending_percentage = (pending_count / total_orders * 100) if total_orders > 0 else 0
    delivered_percentage = (delivered_count / total_orders * 100) if total_orders > 0 else 0
    other_count = total_orders - pending_count - delivered_count
    other_percentage = 100 - pending_percentage - delivered_percentage
    
    # Filter by status if provided
    status = request.GET.get('status')
    if status:
        orders = orders.filter(status=status)
    
    # Sort orders
    sort_by = request.GET.get('sort', 'latest')
    if sort_by == 'oldest':
        orders = orders.order_by('created_at')
    elif sort_by == 'price_high':
        orders = orders.order_by('-total_amount')
    elif sort_by == 'price_low':
        orders = orders.order_by('total_amount')
    
    # Pagination
    paginator = Paginator(orders, 10)  # 10 orders per page
    page = request.GET.get('page')
    orders_page = paginator.get_page(page)
    
    context = {
        'orders': orders_page,
        'total_orders': total_orders,
        'pending_count': pending_count,
        'delivered_count': delivered_count,
        'processing_count': processing_count,
        'shipped_count': shipped_count,
        'pending_percentage': pending_percentage,
        'delivered_percentage': delivered_percentage,
        'other_count': other_count,
        'other_percentage': other_percentage,
    }
    
    return render(request, 'orders/order_list.html', context)

@login_required
def order_id_redirect(request, order_id):
    """Redirect numeric order IDs to order number URLs"""
    try:
        order = Order.objects.get(id=order_id, user=request.user)
        return redirect('orders:order_detail', order_number=order.order_number)
    except Order.DoesNotExist:
        messages.error(request, 'Order not found.')
        return redirect('orders:order_list')

@login_required
def order_detail(request, order_number):
    """Order detail view"""
    order = get_object_or_404(Order, order_number=order_number, user=request.user)
    
    # Get timeline steps for order status
    timeline_steps = get_timeline_steps(order)
    
    context = {
        'order': order,
        'order_items': order.items.all(),
        'timeline_steps': timeline_steps,
        'can_cancel': order.can_cancel,
        'can_return': order.can_return,
    }
    
    return render(request, 'orders/track.html', context)

@login_required
@ratelimit(key='user', rate='5/m')
def create_order(request):
    """Create order from cart"""
    if request.method == 'POST':
        try:
            cart = Cart.objects.get(user=request.user)
            cart_items = cart.items.select_related('product').all()
            
            if not cart_items:
                messages.error(request, 'Your cart is empty.')
                return redirect('cart:cart')
            
            # Get shipping data
            shipping_method = request.POST.get('shipping_method', 'standard')
            shipping_data = {
                'address': request.POST.get('address'),
                'city': request.POST.get('city'),
                'state': request.POST.get('state'),
                'country': request.POST.get('country'),
                'zip_code': request.POST.get('zip_code'),
                'phone': request.POST.get('phone'),
            }
            
            # Calculate totals
            subtotal = cart.total_price
            shipping_cost = calculate_shipping_cost(cart, shipping_method)
            tax_amount = calculate_tax(subtotal, request.POST.get('state', ''))
            discount_amount = request.session.get('discount_amount', 0)
            total_amount = subtotal + shipping_cost + tax_amount - discount_amount
            
            # Create order
            order = Order.objects.create(
                user=request.user,
                subtotal=subtotal,
                shipping_cost=shipping_cost,
                tax_amount=tax_amount,
                discount_amount=discount_amount,
                total_amount=total_amount,
                payment_method=request.POST.get('payment_method', 'card'),
                shipping_address=shipping_data['address'],
                shipping_city=shipping_data['city'],
                shipping_state=shipping_data['state'],
                shipping_country=shipping_data['country'],
                shipping_zip_code=shipping_data['zip_code'],
                shipping_phone=shipping_data['phone'],
                billing_address=request.POST.get('billing_address', ''),
                billing_city=request.POST.get('billing_city', ''),
                billing_state=request.POST.get('billing_state', ''),
                billing_country=request.POST.get('billing_country', ''),
                billing_zip_code=request.POST.get('billing_zip_code', ''),
                customer_notes=request.POST.get('notes', ''),
            )
            
            # Create order items
            for cart_item in cart_items:
                OrderItem.objects.create(
                    order=order,
                    product=cart_item.product,
                    product_name=cart_item.product.name,
                    product_sku=cart_item.product.sku,
                    quantity=cart_item.quantity,
                    unit_price=cart_item.price,
                    total_price=cart_item.total_price,
                    product_data={
                        'name': cart_item.product.name,
                        'description': cart_item.product.description,
                        'image': str(cart_item.product.image.url) if cart_item.product.image else '',
                        'category': cart_item.product.category.name,
                    }
                )
                
                # Update product stock
                cart_item.product.stock -= cart_item.quantity
                cart_item.product.sold_count += cart_item.quantity
                cart_item.product.save()
            
            # Clear cart
            cart.items.all().delete()
            
            # Clear discount from session
            if 'discount_amount' in request.session:
                del request.session['discount_amount']
            
            # Redirect to payment or success page
            payment_method = request.POST.get('payment_method')
            if payment_method in ['paypal', 'paystack', 'momo']:
                return redirect('orders:payment_process', order_id=order.id)
            
            # For card payments, show success page
            return redirect('order_success', order_number=order.order_number)
            
        except Cart.DoesNotExist:
            messages.error(request, 'Cart not found.')
            return redirect('cart:cart')
        except Exception as e:
            messages.error(request, f'Error creating order: {str(e)}')
            return redirect('orders:checkout')
    
    # GET request - show order creation form
    try:
        cart = Cart.objects.get(user=request.user)
        cart_items = cart.items.select_related('product').all()
        
        if not cart_items:
            messages.error(request, 'Your cart is empty.')
            return redirect('cart:cart')
        
        context = {
            'cart_items': cart_items,
            'cart_total': cart.total_price,
            'cart_tax': calculate_tax(cart.total_price, ''),
            'cart_discount': request.session.get('discount_amount', 0),
            'cart_grand_total': cart.total_price + calculate_tax(cart.total_price, '') - request.session.get('discount_amount', 0),
        }
        
        return render(request, 'orders/create.html', context)
    
    except Cart.DoesNotExist:
        messages.error(request, 'Cart not found.')
        return redirect('cart:cart')

def calculate_shipping_cost(cart, shipping_method):
    """Calculate shipping cost based on method"""
    if cart.total_price > 50:
        return 0  # Free shipping
    
    shipping_costs = {
        'standard': 5.99,
        'express': 12.99,
        'overnight': 24.99,
    }
    
    return shipping_costs.get(shipping_method, 5.99)

def calculate_tax(subtotal, state):
    """Calculate tax based on state"""
    tax_rates = {
        'CA': 0.0725,  # California
        'NY': 0.08875,  # New York
        'TX': 0.0625,  # Texas
    }
    
    rate = tax_rates.get(state, 0.06)  # Default 6%
    return subtotal * rate

@login_required
def order_success(request, order_number):
    """Order success page"""
    order = get_object_or_404(Order, order_number=order_number, user=request.user)
    
    context = {
        'order': order,
        'order_items': order.items.all(),
    }
    
    return render(request, 'orders/success.html', context)

@login_required
@ratelimit(key='user', rate='3/m')
def cancel_order(request, order_number):
    """Cancel order"""
    order = get_object_or_404(Order, order_number=order_number, user=request.user)
    
    if order.can_cancel:
        order.status = 'cancelled'
        order.save()
        
        # Restore product stock
        for item in order.items.all():
            try:
                product = item.product
                product.stock += item.quantity
                product.sold_count -= item.quantity
                product.save()
            except:
                pass
        
        messages.success(request, f'Order {order_number} has been cancelled.')
    else:
        messages.error(request, 'This order cannot be cancelled.')
    
    return redirect('orders:order_detail', order_number=order_number)

@login_required
def create_return_request(request, order_number, item_id):
    """Create return request for order item"""
    order = get_object_or_404(Order, order_number=order_number, user=request.user)
    order_item = get_object_or_404(OrderItem, id=item_id, order=order)
    
    if request.method == 'POST':
        reason = request.POST.get('reason')
        description = request.POST.get('description')
        condition = request.POST.get('condition', 'new')
        refund_preference = request.POST.get('refund_preference', 'original')
        shipping_method = request.POST.get('shipping_method', 'label')
        
        if not order.can_return:
            messages.error(request, 'This item cannot be returned.')
            return redirect('order_detail', order_number=order_number)
        
        # Check for existing return request
        existing_return = ReturnRequest.objects.filter(
            order=order,
            order_item=order_item,
            status='pending'
        ).exists()
        
        if existing_return:
            messages.warning(request, 'A return request already exists for this item.')
        else:
            ReturnRequest.objects.create(
                order=order,
                order_item=order_item,
                user=request.user,
                reason=reason,
                description=description,
                metadata={
                    'condition': condition,
                    'refund_preference': refund_preference,
                    'shipping_method': shipping_method,
                }
            )
            messages.success(request, 'Return request submitted successfully.')
        
        return redirect('order_detail', order_number=order_number)
    
    # GET request - show return form
    return_reasons = [
        ('defective', 'Defective Product'),
        ('wrong_item', 'Wrong Item Received'),
        ('not_as_described', 'Not as Described'),
        ('changed_mind', 'Changed Mind'),
        ('damaged', 'Damaged During Shipping'),
        ('other', 'Other'),
    ]
    
    context = {
        'order': order,
        'order_item': order_item,
        'return_reasons': return_reasons,
    }
    
    return render(request, 'orders/return_request.html', context)

@login_required
def track_order(request, order_number):
    """Track order status"""
    order = get_object_or_404(Order, order_number=order_number, user=request.user)
    
    # Get tracking updates
    tracking_updates = []
    
    # Order placed
    tracking_updates.append({
        'status': 'Order Placed',
        'date': order.created_at,
        'description': 'Order has been placed successfully',
        'location': 'Online Store',
    })
    
    # Payment confirmed
    if order.paid_at:
        tracking_updates.append({
            'status': 'Payment Confirmed',
            'date': order.paid_at,
            'description': 'Payment has been confirmed',
            'location': 'Payment Gateway',
        })
    
    # Order confirmed
    if order.status in ['confirmed', 'processing', 'shipped', 'delivered']:
        tracking_updates.append({
            'status': 'Order Confirmed',
            'date': order.created_at + timedelta(hours=1),
            'description': 'Order has been confirmed and is being processed',
            'location': 'Warehouse',
        })
    
    # Order processing
    if order.status in ['processing', 'shipped', 'delivered']:
        tracking_updates.append({
            'status': 'Order Processing',
            'date': order.created_at + timedelta(hours=2),
            'description': 'Order is being prepared for shipment',
            'location': 'Warehouse',
        })
    
    # Order shipped
    if order.status in ['shipped', 'delivered'] and order.shipped_at:
        tracking_updates.append({
            'status': 'Order Shipped',
            'date': order.shipped_at,
            'description': 'Order has been shipped',
            'location': 'Warehouse',
        })
    
    # Order delivered
    if order.status == 'delivered' and order.delivered_at:
        tracking_updates.append({
            'status': 'Order Delivered',
            'date': order.delivered_at,
            'description': 'Order has been delivered',
            'location': 'Delivery Address',
        })
    
    # Calculate estimated delivery
    estimated_delivery = None
    if order.shipped_at:
        estimated_delivery = order.shipped_at + timedelta(days=3)
    elif order.status in ['confirmed', 'processing']:
        estimated_delivery = order.created_at + timedelta(days=5)
    
    context = {
        'order': order,
        'tracking_updates': tracking_updates,
        'estimated_delivery': estimated_delivery,
    }
    
    return render(request, 'orders/track.html', context)

def get_timeline_steps(order):
    """Get timeline steps for order status"""
    steps = [
        {
            'title': 'Order Placed',
            'description': 'Order has been placed',
            'icon': 'fas fa-shopping-cart',
            'completed': True,
            'current': order.status == 'pending',
            'date': order.created_at,
        },
        {
            'title': 'Order Confirmed',
            'description': 'Order has been confirmed',
            'icon': 'fas fa-check-circle',
            'completed': order.status in ['confirmed', 'processing', 'shipped', 'delivered'],
            'current': order.status == 'confirmed',
            'date': order.created_at + timedelta(hours=1) if order.status in ['confirmed', 'processing', 'shipped', 'delivered'] else None,
        },
        {
            'title': 'Order Processing',
            'description': 'Order is being processed',
            'icon': 'fas fa-cog',
            'completed': order.status in ['processing', 'shipped', 'delivered'],
            'current': order.status == 'processing',
            'date': order.created_at + timedelta(hours=2) if order.status in ['processing', 'shipped', 'delivered'] else None,
        },
        {
            'title': 'Order Shipped',
            'description': 'Order has been shipped',
            'icon': 'fas fa-shipping-fast',
            'completed': order.status in ['shipped', 'delivered'],
            'current': order.status == 'shipped',
            'date': order.shipped_at,
        },
        {
            'title': 'Order Delivered',
            'description': 'Order has been delivered',
            'icon': 'fas fa-home',
            'completed': order.status == 'delivered',
            'current': order.status == 'delivered',
            'date': order.delivered_at,
        },
    ]
    return steps

def generate_invoice_pdf(order):
    """Generate PDF invoice for order"""
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    
    # Title
    p.setFont("Helvetica-Bold", 24)
    p.drawString(100, 750, "INVOICE")
    
    # Company Information
    p.setFont("Helvetica", 10)
    p.drawString(100, 720, "TechStore E-commerce")
    p.drawString(100, 705, "123 Business Street")
    p.drawString(100, 690, "San Francisco, CA 94107")
    p.drawString(100, 675, "contact@techstore.com")
    
    # Invoice Details
    p.setFont("Helvetica-Bold", 12)
    p.drawString(400, 750, f"Invoice #: INV-{order.order_number}")
    p.setFont("Helvetica", 10)
    p.drawString(400, 735, f"Date: {order.created_at.strftime('%B %d, %Y')}")
    p.drawString(400, 720, f"Order #: {order.order_number}")
    
    # Customer Information
    p.setFont("Helvetica-Bold", 12)
    p.drawString(100, 620, "Bill To:")
    p.setFont("Helvetica", 10)
    p.drawString(100, 605, order.user.get_full_name() or order.user.username)
    p.drawString(100, 590, order.shipping_address)
    p.drawString(100, 575, f"{order.shipping_city}, {order.shipping_state} {order.shipping_zip_code}")
    p.drawString(100, 560, order.shipping_country)
    p.drawString(100, 545, f"Phone: {order.shipping_phone}")
    
    # Table Header
    p.setFont("Helvetica-Bold", 10)
    p.drawString(100, 500, "Description")
    p.drawString(300, 500, "Quantity")
    p.drawString(350, 500, "Unit Price")
    p.drawString(450, 500, "Total")
    
    # Table Rows
    y = 480
    for item in order.items.all():
        p.setFont("Helvetica", 10)
        p.drawString(100, y, item.product_name[:40])
        p.drawString(300, y, str(item.quantity))
        p.drawString(350, y, f"${item.unit_price:.2f}")
        p.drawString(450, y, f"${item.total_price:.2f}")
        y -= 20
    
    # Summary
    y -= 40
    p.setFont("Helvetica", 10)
    p.drawString(350, y, "Subtotal:")
    p.drawString(450, y, f"${order.subtotal:.2f}")
    
    y -= 20
    p.drawString(350, y, "Shipping:")
    p.drawString(450, y, f"${order.shipping_cost:.2f}")
    
    y -= 20
    p.drawString(350, y, "Tax:")
    p.drawString(450, y, f"${order.tax_amount:.2f}")
    
    y -= 20
    if order.discount_amount > 0:
        p.drawString(350, y, "Discount:")
        p.drawString(450, y, f"-${order.discount_amount:.2f}")
        y -= 20
    
    y -= 20
    p.setFont("Helvetica-Bold", 12)
    p.drawString(350, y, "Total:")
    p.drawString(450, y, f"${order.total_amount:.2f}")
    
    # Footer
    p.setFont("Helvetica", 8)
    p.drawString(100, 100, "Thank you for your business!")
    p.drawString(100, 85, "Terms & Conditions apply.")
    
    p.showPage()
    p.save()
    
    buffer.seek(0)
    return buffer

# In orders/views.py, update the download_invoice function:

@login_required
def download_invoice(request, order_number):
    """Download order invoice as PDF"""
    try:
        # For admin users, allow access to any order
        if request.user.is_staff or request.user.is_superuser or getattr(request.user, 'role', '') == 'admin':
            order = get_object_or_404(Order, order_number=order_number)
        else:
            # For regular users, only their own orders
            order = get_object_or_404(Order, order_number=order_number, user=request.user)
        
        # Check if invoice exists
        try:
            invoice = order.invoice
        except Invoice.DoesNotExist:
            # Create invoice if it doesn't exist
            invoice = Invoice.objects.create(
                order=order,
                invoice_number=f"INV-{order.order_number}",
            )
        
        # Generate PDF
        pdf_buffer = generate_invoice_pdf(order)
        
        # Save to file if not already saved
        if not invoice.pdf_file:
            from django.core.files.base import ContentFile
            pdf_content = ContentFile(pdf_buffer.getvalue())
            invoice.pdf_file.save(f'invoice_{order_number}.pdf', pdf_content)
            invoice.save()
        
        # Return PDF as response
        response = HttpResponse(pdf_buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="invoice_{order_number}.pdf"'
        return response
        
    except Order.DoesNotExist:
        messages.error(request, 'Order not found.')
        return redirect('orders:order_list')
    except Exception as e:
        messages.error(request, f'Error generating invoice: {str(e)}')
        return redirect('orders:order_detail', order_number=order_number)

# Add this to your orders/views.py for better error handling:

@login_required
def download_invoice_fallback(request, order_number):
    """Safer invoice download with better error handling"""
    try:
        # Check if user can access this order
        if hasattr(request.user, 'is_staff') and (request.user.is_staff or request.user.is_superuser):
            # Admin can see all orders
            orders = Order.objects.filter(order_number=order_number)
        else:
            # Regular users can only see their own orders
            orders = Order.objects.filter(order_number=order_number, user=request.user)
        
        if not orders.exists():
            messages.error(request, f'Order {order_number} not found or you do not have permission to access it.')
            return redirect('orders:order_list')
        
        order = orders.first()
        
        # Generate PDF
        pdf_buffer = generate_invoice_pdf(order)
        
        # Return PDF
        response = HttpResponse(pdf_buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="invoice_{order_number}.pdf"'
        return response
        
    except Exception as e:
        messages.error(request, f'Error generating invoice: {str(e)}')
        return redirect('orders:order_list')
    
# orders/admin_views.py - Add this file
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone
from datetime import datetime, timedelta
from .models import Order, ReturnRequest

def is_admin_or_staff(user):
    """Check if user is admin or staff"""
    return user.is_authenticated and (user.is_staff or user.is_superuser or getattr(user, 'role', '') == 'admin')

@login_required
@user_passes_test(is_admin_or_staff)
def admin_order_list(request):
    """Admin order listing"""
    from django.db.models import Count
    
    orders = Order.objects.all().select_related('user').prefetch_related('items').annotate(
        item_count=Count('items', distinct=True)
    )
    
    # Apply filters
    status_filter = request.GET.get('status', '')
    payment_filter = request.GET.get('payment_status', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    search_query = request.GET.get('q', '')
    
    if status_filter:
        orders = orders.filter(status=status_filter)
    
    if payment_filter:
        orders = orders.filter(payment_status=payment_filter)
    
    if date_from:
        try:
            date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            orders = orders.filter(created_at__date__gte=date_from)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            orders = orders.filter(created_at__date__lte=date_to)
        except ValueError:
            pass
    
    if search_query:
        orders = orders.filter(
            Q(order_number__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(shipping_city__icontains=search_query) |
            Q(shipping_state__icontains=search_query)
        )
    
    # Order stats
    order_stats = {
        'total': Order.objects.count(),
        'pending': Order.objects.filter(status='pending').count(),
        'processing': Order.objects.filter(status='processing').count(),
        'shipped': Order.objects.filter(status='shipped').count(),
        'delivered': Order.objects.filter(status='delivered').count(),
        'cancelled': Order.objects.filter(status='cancelled').count(),
        'today': Order.objects.filter(created_at__date=timezone.now().date()).count(),
        'week': Order.objects.filter(created_at__date__gte=timezone.now().date() - timedelta(days=7)).count(),
    }
    
    # Today's revenue
    today_revenue = Order.objects.filter(
        created_at__date=timezone.now().date(),
        payment_status='paid'
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    
    # Pagination
    paginator = Paginator(orders.order_by('-created_at'), 20)
    page = request.GET.get('page')
    orders = paginator.get_page(page)
    
    context = {
        'orders': orders,
        'order_stats': order_stats,
        'today_revenue': today_revenue,
        'query_params': request.GET.urlencode(),
    }
    
    return render(request, 'admin/orders/admin_list.html', context)

@login_required
@user_passes_test(is_admin_or_staff)
def admin_order_detail(request, order_number):
    """Admin order detail view"""
    order = get_object_or_404(Order, order_number=order_number)
    
    context = {
        'order': order,
        'order_items': order.items.all(),
    }
    
    return render(request, 'admin/orders/admin_detail.html', context)

@login_required
@user_passes_test(is_admin_or_staff)
def admin_update_order_status(request, order_number):
    """Update order status"""
    if request.method == 'POST':
        order = get_object_or_404(Order, order_number=order_number)
        new_status = request.POST.get('status')
        
        if new_status in dict(Order.ORDER_STATUS_CHOICES):
            old_status = order.status
            order.status = new_status
            
            # Update timestamps
            if new_status == 'shipped' and not order.shipped_at:
                order.shipped_at = timezone.now()
            elif new_status == 'delivered' and not order.delivered_at:
                order.delivered_at = timezone.now()
            
            order.save()
            
            # Create status history
            from .models import OrderStatusHistory
            OrderStatusHistory.objects.create(
                order=order,
                old_status=old_status,
                new_status=new_status,
                notes=request.POST.get('notes', ''),
                created_by=request.user
            )
            
            # Send email to customer about status update
            try:
                send_order_status_update_email(order, old_status, new_status)
            except Exception as e:
                print(f"Warning: Could not send status update email - {str(e)}")
            
            messages.success(request, f'Order status updated to {order.get_status_display()} and customer notified')
        else:
            messages.error(request, 'Invalid status')
    
    return redirect('orders:admin_order_detail', order_number=order_number)

@login_required
@user_passes_test(is_admin_or_staff)
def admin_update_payment_status(request, order_number):
    """Update payment status"""
    if request.method == 'POST':
        order = get_object_or_404(Order, order_number=order_number)
        new_status = request.POST.get('payment_status')
        
        if new_status in dict(Order.PAYMENT_STATUS_CHOICES):
            old_status = order.payment_status
            order.payment_status = new_status
            
            # Update paid_at if marked as paid
            if new_status == 'paid' and not order.paid_at:
                order.paid_at = timezone.now()
            
            order.save()
            
            # Send email to customer about payment status update
            try:
                send_payment_status_update_email(order, old_status, new_status)
            except Exception as e:
                print(f"Warning: Could not send payment status update email - {str(e)}")
            
            messages.success(request, f'Payment status updated to {order.get_payment_status_display()} and customer notified')
        else:
            messages.error(request, 'Invalid payment status')
    
    return redirect('orders:admin_order_detail', order_number=order_number)

@login_required
@user_passes_test(is_admin_or_staff)
def admin_return_list(request):
    """Admin return request listing"""
    returns = ReturnRequest.objects.all().select_related('order', 'user', 'order_item')
    
    # Apply filters
    status_filter = request.GET.get('status', '')
    if status_filter:
        returns = returns.filter(status=status_filter)
    
    # Stats
    return_stats = {
        'total': ReturnRequest.objects.count(),
        'pending': ReturnRequest.objects.filter(status='pending').count(),
        'approved': ReturnRequest.objects.filter(status='approved').count(),
        'rejected': ReturnRequest.objects.filter(status='rejected').count(),
        'completed': ReturnRequest.objects.filter(status='completed').count(),
    }
    
    # Pagination
    paginator = Paginator(returns.order_by('-requested_at'), 20)
    page = request.GET.get('page')
    returns = paginator.get_page(page)
    
    context = {
        'returns': returns,
        'return_stats': return_stats,
    }
    
    return render(request, 'admin/orders/admin_return_list.html', context)

@login_required
@user_passes_test(is_admin_or_staff)
def admin_return_detail(request, return_id):
    """Admin return request detail"""
    return_request = get_object_or_404(ReturnRequest, id=return_id)
    
    context = {
        'return_request': return_request,
    }
    
    return render(request, 'admin/orders/admin_return_detail.html', context)

@login_required
@user_passes_test(is_admin_or_staff)
def admin_update_return_status(request, return_id):
    """Update return request status"""
    if request.method == 'POST':
        return_request = get_object_or_404(ReturnRequest, id=return_id)
        new_status = request.POST.get('status')
        
        if new_status in dict(ReturnRequest.RETURN_STATUS_CHOICES):
            return_request.status = new_status
            
            # Update resolved_at if not pending
            if new_status != 'pending' and not return_request.resolved_at:
                return_request.resolved_at = timezone.now()
            
            # Update refund amount if provided
            refund_amount = request.POST.get('refund_amount')
            if refund_amount:
                try:
                    return_request.refund_amount = float(refund_amount)
                except ValueError:
                    pass
            
            return_request.resolution = request.POST.get('resolution', '')
            return_request.save()
            
            messages.success(request, f'Return request status updated to {return_request.get_status_display()}')
        else:
            messages.error(request, 'Invalid status')
    
    return redirect('orders:admin_return_detail', return_id=return_id)

@login_required
@user_passes_test(is_admin_or_staff)
def admin_dashboard_orders(request):
    """Orders dashboard for admin"""
    
    # Date ranges
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    
    # Stats
    today_orders = Order.objects.filter(created_at__date=today)
    today_revenue = today_orders.filter(payment_status='paid').aggregate(total=Sum('total_amount'))['total'] or 0
    
    week_orders = Order.objects.filter(created_at__date__gte=week_ago)
    week_revenue = week_orders.filter(payment_status='paid').aggregate(total=Sum('total_amount'))['total'] or 0
    
    month_orders = Order.objects.filter(created_at__date__gte=month_ago)
    month_revenue = month_orders.filter(payment_status='paid').aggregate(total=Sum('total_amount'))['total'] or 0
    
    # Order status distribution
    order_status_dist = Order.objects.values('status').annotate(
        count=Count('id')
    ).order_by('status')
    
    # Payment status distribution
    payment_status_dist = Order.objects.values('payment_status').annotate(
        count=Count('id')
    ).order_by('payment_status')
    
    # Recent orders
    recent_orders = Order.objects.select_related('user').order_by('-created_at')[:10]
    
    # Top customers
    top_customers = Order.objects.values('user__username', 'user__email').annotate(
        order_count=Count('id'),
        total_spent=Sum('total_amount')
    ).order_by('-total_spent')[:5]
    
    context = {
        'today_orders_count': today_orders.count(),
        'today_revenue': today_revenue,
        'week_orders_count': week_orders.count(),
        'week_revenue': week_revenue,
        'month_orders_count': month_orders.count(),
        'month_revenue': month_revenue,
        'order_status_dist': order_status_dist,
        'payment_status_dist': payment_status_dist,
        'recent_orders': recent_orders,
        'top_customers': top_customers,
        'today': today,
    }
    
    return render(request, 'admin/orders/admin_dashboard.html', context)

# Add these functions to your orders/views.py

@login_required
@user_passes_test(is_admin_or_staff)
def admin_update_tracking(request, order_number):
    """Update tracking information"""
    if request.method == 'POST':
        order = get_object_or_404(Order, order_number=order_number)
        tracking_number = request.POST.get('tracking_number', '').strip()
        carrier = request.POST.get('carrier', '').strip()
        
        if tracking_number:
            order.tracking_number = tracking_number
            order.carrier = carrier
            order.status = 'shipped'
            if not order.shipped_at:
                order.shipped_at = timezone.now()
            order.save()
            
            # Add status history
            from .models import OrderStatusHistory
            OrderStatusHistory.objects.create(
                order=order,
                old_status=order.status,
                new_status='shipped',
                notes=f'Tracking added: {tracking_number} ({carrier})',
                created_by=request.user
            )
            
            messages.success(request, 'Tracking information updated and order marked as shipped.')
        else:
            messages.error(request, 'Please enter a tracking number.')
    
    return redirect('orders:admin_order_detail', order_number=order_number)

@login_required
@user_passes_test(is_admin_or_staff)
def export_order_csv(request, order_number):
    """Export order details as CSV"""
    import csv
    from django.http import HttpResponse
    
    order = get_object_or_404(Order, order_number=order_number)
    
    # Create HTTP response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="order_{order_number}.csv"'
    
    writer = csv.writer(response)
    
    # Write header
    writer.writerow(['Order Export - Order Number:', order.order_number])
    writer.writerow(['Export Date:', timezone.now().strftime('%Y-%m-%d %H:%M:%S')])
    writer.writerow([])
    
    # Order details
    writer.writerow(['ORDER DETAILS'])
    writer.writerow(['Order Number:', order.order_number])
    writer.writerow(['Date:', order.created_at.strftime('%Y-%m-%d %H:%M:%S')])
    writer.writerow(['Status:', order.get_status_display()])
    writer.writerow(['Payment Status:', order.get_payment_status_display()])
    writer.writerow(['Payment Method:', order.payment_method])
    writer.writerow(['Transaction ID:', order.transaction_id or 'N/A'])
    writer.writerow([])
    
    # Customer details
    writer.writerow(['CUSTOMER DETAILS'])
    writer.writerow(['Customer ID:', order.user.id])
    writer.writerow(['Username:', order.user.username])
    writer.writerow(['Email:', order.user.email])
    writer.writerow(['Full Name:', order.user.get_full_name() or 'N/A'])
    writer.writerow([])
    
    # Shipping details
    writer.writerow(['SHIPPING ADDRESS'])
    writer.writerow(['Address:', order.shipping_address])
    writer.writerow(['City:', order.shipping_city])
    writer.writerow(['State:', order.shipping_state])
    writer.writerow(['Zip Code:', order.shipping_zip_code])
    writer.writerow(['Country:', order.shipping_country])
    writer.writerow(['Phone:', order.shipping_phone])
    writer.writerow([])
    
    # Billing details
    writer.writerow(['BILLING ADDRESS'])
    writer.writerow(['Address:', order.billing_address or 'Same as shipping'])
    writer.writerow(['City:', order.billing_city or ''])
    writer.writerow(['State:', order.billing_state or ''])
    writer.writerow(['Zip Code:', order.billing_zip_code or ''])
    writer.writerow(['Country:', order.billing_country or ''])
    writer.writerow([])
    
    # Order items
    writer.writerow(['ORDER ITEMS'])
    writer.writerow(['Product Name', 'SKU', 'Quantity', 'Unit Price', 'Total Price'])
    
    for item in order.items.all():
        writer.writerow([
            item.product_name,
            item.product_sku,
            item.quantity,
            f"${item.unit_price:.2f}",
            f"${item.total_price:.2f}"
        ])
    
    writer.writerow([])
    
    # Order summary
    writer.writerow(['ORDER SUMMARY'])
    writer.writerow(['Subtotal:', f"${order.subtotal:.2f}"])
    writer.writerow(['Shipping:', f"${order.shipping_cost:.2f}"])
    writer.writerow(['Tax:', f"${order.tax_amount:.2f}"])
    if order.discount_amount > 0:
        writer.writerow(['Discount:', f"-${order.discount_amount:.2f}"])
    writer.writerow(['Total Amount:', f"${order.total_amount:.2f}"])
    
    return response

@login_required
@user_passes_test(is_admin_or_staff)
def admin_order_edit(request, order_number):
    """Edit order details"""
    order = get_object_or_404(Order, order_number=order_number)
    
    if request.method == 'POST':
        # Update shipping information
        order.shipping_address = request.POST.get('shipping_address', order.shipping_address)
        order.shipping_city = request.POST.get('shipping_city', order.shipping_city)
        order.shipping_state = request.POST.get('shipping_state', order.shipping_state)
        order.shipping_zip_code = request.POST.get('shipping_zip_code', order.shipping_zip_code)
        order.shipping_country = request.POST.get('shipping_country', order.shipping_country)
        order.shipping_phone = request.POST.get('shipping_phone', order.shipping_phone)
        
        # Update billing information
        order.billing_address = request.POST.get('billing_address', order.billing_address)
        order.billing_city = request.POST.get('billing_city', order.billing_city)
        order.billing_state = request.POST.get('billing_state', order.billing_state)
        order.billing_zip_code = request.POST.get('billing_zip_code', order.billing_zip_code)
        order.billing_country = request.POST.get('billing_country', order.billing_country)
        
        # Update customer notes
        order.customer_notes = request.POST.get('customer_notes', order.customer_notes)
        order.admin_notes = request.POST.get('admin_notes', order.admin_notes)
        
        order.save()
        messages.success(request, 'Order details updated successfully.')
        return redirect('orders:admin_order_detail', order_number=order.order_number)
    
    context = {
        'order': order,
    }
    return render(request, 'admin/orders/admin_edit.html', context)

@login_required
@user_passes_test(is_admin_or_staff)
def admin_order_detail_modal(request, order_number):
    """Admin order detail view for modal (AJAX)"""
    order = get_object_or_404(Order, order_number=order_number)
    
    context = {
        'order': order,
        'order_items': order.items.all(),
        'order_status_choices': Order.ORDER_STATUS_CHOICES,  
        'payment_status_choices': Order.PAYMENT_STATUS_CHOICES,
        'modal_view': True,  # Flag to indicate this is for modal view
    }
    
    return render(request, 'admin/orders/_order_detail_content.html', context)


@login_required
@user_passes_test(is_admin_or_staff)
def admin_order_delete(request, order_number):
    """Delete order via AJAX"""
    from django.http import JsonResponse
    
    order = get_object_or_404(Order, order_number=order_number)
    
    if request.method == 'POST':
        try:
            order_num = order.order_number
            order.delete()
            
            # Check if it's an AJAX request
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.content_type == 'application/json':
                return JsonResponse({
                    'success': True,
                    'message': f'Order {order_num} has been deleted successfully!'
                })
            else:
                messages.success(request, f'Order {order_num} deleted successfully!')
                return redirect('orders:admin_order_list')
        except Exception as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.content_type == 'application/json':
                return JsonResponse({
                    'success': False,
                    'message': f'Error deleting order: {str(e)}'
                }, status=400)
            else:
                messages.error(request, f'Error deleting order: {str(e)}')
                return redirect('orders:admin_order_list')
    
    # GET request - shouldn't be used anymore but keeping for compatibility
    from django.http import HttpResponseNotAllowed
    return HttpResponseNotAllowed(['POST'])

# Add or update this function in orders/views.py
from django.http import JsonResponse

@login_required
def order_details_api(request, order_id):
    """API endpoint to get order details for AJAX request"""
    try:
        # Check if user can access this order
        if request.user.is_staff or request.user.is_superuser:
            order = get_object_or_404(Order, id=order_id)
        else:
            # Regular users can only see their own orders
            order = get_object_or_404(Order, id=order_id, user=request.user)
        
        # Prepare order data
        order_data = {
            'success': True,
            'order': {
                'id': order.id,
                'order_number': order.order_number,
                'subtotal': float(order.subtotal),
                'shipping_cost': float(order.shipping_cost),
                'tax_amount': float(order.tax_amount),
                'discount_amount': float(order.discount_amount),
                'total_amount': float(order.total_amount),
                'tracking_number': order.tracking_number or '',
                'carrier': order.carrier or '',
                'shipping_address': order.shipping_address or '',
                'shipping_city': order.shipping_city or '',
                'shipping_state': order.shipping_state or '',
                'shipping_zip_code': order.shipping_zip_code or '',
                'shipping_country': order.shipping_country or '',
                'shipping_phone': order.shipping_phone or '',
                'shipping_name': f"{order.user.first_name} {order.user.last_name}".strip() or order.user.username,
                'customer_name': order.user.get_full_name() or order.user.username,
                'status': order.status,
                'payment_status': order.payment_status,
                'created_at': order.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'items': []
            }
        }
        
        # Add order items
        for item in order.items.all():
            # Get image URL safely
            image_url = None
            if item.product and hasattr(item.product, 'primary_image_url'):
                image_url = item.product.primary_image_url
            elif item.product and hasattr(item.product, 'image') and item.product.image:
                image_url = item.product.image.url
            
            order_data['order']['items'].append({
                'id': item.id,
                'product_name': item.product_name,
                'product_sku': item.product_sku,
                'quantity': item.quantity,
                'unit_price': float(item.unit_price),
                'total_price': float(item.total_price),
                'image_url': image_url
            })
        
        return JsonResponse(order_data)
        
    except Order.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Order not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)