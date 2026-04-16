# apps/cart/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseBadRequest
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_http_methods
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django_ratelimit.decorators import ratelimit
import json

from .models import Cart, CartItem
from products.models import Product



def get_or_create_cart(request):
    """
    Get or create cart based on user authentication status.
    Merges session cart with user cart on login.
    """
    if request.user.is_authenticated:
        # Try to get user's active cart
        cart, created = Cart.objects.get_or_create(
            user=request.user,
            is_active=True
        )
        
        # If user has session cart from before login, merge it
        session_key = request.session.get('cart_session_key')
        if session_key and not created:
            try:
                session_cart = Cart.objects.get(
                    session_key=session_key,
                    user=None,
                    is_active=True
                )
                cart.merge_with_session_cart(session_cart)
                # Clear session key after merge
                request.session.pop('cart_session_key', None)
            except Cart.DoesNotExist:
                pass
    else:
        # For anonymous users, use session-based cart
        session_key = request.session.session_key
        if not session_key:
            request.session.create()
            session_key = request.session.session_key
        
        cart, created = Cart.objects.get_or_create(
            session_key=session_key,
            user=None,
            defaults={'is_active': True}
        )
        
        # Store session key for potential future merge
        if created:
            request.session['cart_session_key'] = session_key
    
    return cart


@ratelimit(key='ip', rate='30/m', method='GET')
def cart_view(request):
    """Display cart contents"""
    from decimal import Decimal
    
    cart = get_or_create_cart(request)
    cart_items = cart.items.select_related('product').all()
    
    # Check availability and update prices
    unavailable_items = []
    for item in cart_items:
        item.update_price_if_needed()
        if not item.is_available:
            unavailable_items.append(item)
    
    # Calculate totals using Decimal to ensure correlation
    cart_total_decimal = Decimal(str(cart.total_price))
    cart_tax_decimal = (cart_total_decimal * Decimal('0.1')).quantize(Decimal('0.01'))
    cart_discount = Decimal('0')  # Will be updated if promo applied
    
    # Check for applied promo code in session
    applied_promo = request.session.get('applied_promo')
    if applied_promo:
        cart_discount = Decimal(str(applied_promo.get('discount', 0)))
    
    # Determine shipping cost
    shipping_cost_decimal = Decimal('0') if cart_total_decimal > Decimal('50') else Decimal('5.99')
    
    # Calculate grand total
    cart_grand_total_decimal = (cart_total_decimal + cart_tax_decimal + shipping_cost_decimal - cart_discount).quantize(Decimal('0.01'))
    
    context = {
        'cart': cart,
        'cart_items': cart_items,
        'cart_total': float(cart_total_decimal),
        'cart_quantity': cart.total_quantity,
        'cart_tax': float(cart_tax_decimal),
        'cart_discount': float(cart_discount),
        'cart_grand_total': float(cart_grand_total_decimal),
        'shipping_cost': float(shipping_cost_decimal),
        'subtotal': float(cart_total_decimal),
        'unavailable_items': unavailable_items,
        'has_unavailable_items': bool(unavailable_items),
    }
    return render(request, 'cart/cart.html', context)


# In cart/views.py - Update add_to_cart function
# apps/cart/views.py - Replace your add_to_cart function with this

@require_POST
@ratelimit(key='ip', rate='20/m')
def add_to_cart(request, product_id):
    """Add product to cart with AJAX support"""
    try:
        product = get_object_or_404(
            Product, 
            id=product_id, 
            is_active=True
        )
        
        # Get quantity and buy_now flag from request
        try:
            data = json.loads(request.body) if request.body else {}
            quantity = int(data.get('quantity', 1))
            buy_now = data.get('buy_now', False)
        except (json.JSONDecodeError, ValueError):
            quantity = 1
            buy_now = False
        
        # If buy_now is true, user MUST be authenticated
        if buy_now and not request.user.is_authenticated:
            return JsonResponse({
                'success': False,
                'message': 'Please log in to use Buy Now',
                'requires_auth': True
            }, status=401)
        
        # Check stock availability
        if product.stock <= 0:
            return JsonResponse({
                'success': False,
                'message': 'Product is out of stock',
                'stock': product.stock
            })
        
        quantity = max(1, min(quantity, product.stock))
        
        with transaction.atomic():
            cart = get_or_create_cart(request)
            
            # Get current price
            current_price = float(product.discount_price or product.price)
            
            # Try to get existing cart item
            cart_item, created = CartItem.objects.get_or_create(
                cart=cart,
                product=product,
                defaults={
                    'quantity': quantity,
                    'price': current_price
                }
            )
            
            if not created:
                # Update existing item
                new_quantity = cart_item.quantity + quantity
                if new_quantity > product.stock:
                    new_quantity = product.stock
                    message = f"Only {product.stock} items available. Added maximum quantity."
                else:
                    message = f"{product.name} quantity updated to {new_quantity}"
                
                cart_item.quantity = new_quantity
                cart_item.price = current_price
                cart_item.save()
            else:
                message = f"{product.name} added to cart"
            
            # IMPORTANT: Refresh cart and calculate total quantity across ALL items
            cart.refresh_from_db()
            
            # Calculate total quantity - THIS IS CRITICAL
            from django.db.models import Sum
            total_quantity = cart.items.aggregate(total=Sum('quantity'))['total'] or 0
            
            response_data = {
                'success': True,
                'message': message,
                'cart_total': float(cart.total_price),
                'cart_quantity': total_quantity,  # Total number of items in cart
                'cart_count': total_quantity,     # Same value for compatibility
                'item_quantity': cart_item.quantity,
                'product_name': product.name,
                'product_stock': product.stock,
                'buy_now': buy_now,
            }
            
            print(f"Cart updated - Total items: {total_quantity}")  # Debug
            
        return JsonResponse(response_data)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)
        
        
@require_POST
@ratelimit(key='ip', rate='30/m')
def update_cart_item(request, item_id):
    """Update cart item quantity"""
    try:
        data = json.loads(request.body)
        quantity = int(data.get('quantity', 1))
        
        if quantity < 1:
            return JsonResponse({
                'success': False,
                'message': 'Quantity must be at least 1'
            })
        
        cart = get_or_create_cart(request)
        cart_item = get_object_or_404(CartItem, id=item_id, cart=cart)
        
        # Check product stock
        if quantity > cart_item.product.stock:
            quantity = cart_item.product.stock
            message = f"Only {cart_item.product.stock} items available"
        else:
            message = "Quantity updated"
        
        cart_item.quantity = quantity
        cart_item.update_price_if_needed()
        cart_item.save()
        
        # Refresh cart
        cart.refresh_from_db()
        
        return JsonResponse({
            'success': True,
            'message': message,
            'item_total': float(cart_item.total_price),
            'item_quantity': cart_item.quantity,
            'cart_total': float(cart.total_price),
            'cart_quantity': cart.total_quantity,
            'product_stock': cart_item.product.stock,
        })
        
    except CartItem.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Item not found in cart'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)


@require_POST
@ratelimit(key='ip', rate='30/m')
def remove_from_cart(request, item_id):
    """Remove item from cart"""
    try:
        cart = get_or_create_cart(request)
        cart_item = get_object_or_404(CartItem, id=item_id, cart=cart)
        product_name = cart_item.product.name
        cart_item.delete()
        
        # Refresh cart
        cart.refresh_from_db()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': f'{product_name} removed from cart',
                'cart_total': float(cart.total_price),
                'cart_quantity': cart.total_quantity,
            })
        else:
            messages.success(request, f'{product_name} removed from cart')
            return redirect('cart')
            
    except CartItem.DoesNotExist:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'message': 'Item not found'
            }, status=404)
        else:
            messages.error(request, 'Item not found')
            return redirect('cart')


@require_POST
@ratelimit(key='ip', rate='10/m')
def clear_cart(request):
    """Clear all items from cart"""
    try:
        cart = get_or_create_cart(request)
        item_count = cart.items.count()
        cart.clear()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': f'Cart cleared ({item_count} items removed)',
                'cart_total': 0,
                'cart_quantity': 0,
            })
        else:
            messages.success(request, f'Cart cleared ({item_count} items removed)')
            return redirect('cart')
            
    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=400)
        else:
            messages.error(request, f'Error clearing cart: {str(e)}')
            return redirect('cart')


@require_POST
@ratelimit(key='ip', rate='10/m')
def apply_promo_code(request, code):
    """Apply promo code to cart"""
    try:
        cart = get_or_create_cart(request)
        
        # Check if promo code exists and is valid
        promo = get_object_or_404(
            
            code=code.upper(),
            is_active=True,
            valid_from__lte=timezone.now(),
            valid_to__gte=timezone.now()
        )
        
        # Check if promo code can be applied to cart
        if promo.minimum_cart_amount and cart.total_price < promo.minimum_cart_amount:
            return JsonResponse({
                'success': False,
                'message': f'Minimum cart amount of ${promo.minimum_cart_amount} required'
            })
        
        # Check if promo code is already used by user
        if request.user.is_authenticated and promo.is_single_use_per_user:
            if promo.used_by.filter(id=request.user.id).exists():
                return JsonResponse({
                    'success': False,
                    'message': 'Promo code already used'
                })
        
        # Calculate discount
        discount_amount = promo.calculate_discount(cart.total_price)
        
        # Store promo in session or cart metadata
        request.session['applied_promo'] = {
            'code': promo.code,
            'discount': float(discount_amount),
            'type': promo.discount_type,
            'value': float(promo.discount_value),
        }
        
        return JsonResponse({
            'success': True,
            'message': f'Promo code "{promo.code}" applied successfully',
            'discount': float(discount_amount),
            'new_total': float(cart.total_price - discount_amount),
            'promo_code': promo.code,
        })
        
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)


@require_POST
@ratelimit(key='ip', rate='10/m')
def remove_promo_code(request):
    """Remove applied promo code"""
    try:
        if 'applied_promo' in request.session:
            promo_code = request.session['applied_promo']['code']
            del request.session['applied_promo']
            
            return JsonResponse({
                'success': True,
                'message': f'Promo code "{promo_code}" removed',
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'No promo code applied'
            })
            
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)


@require_http_methods(["GET", "POST"])
@login_required
@ratelimit(key='user', rate='5/m')
def save_cart_for_later(request):
    """Save current cart items to wishlist or saved items"""
    if request.method == 'POST':
        try:
            cart = get_or_create_cart(request)
            
            # Implementation depends on your wishlist/saved items model
            # This is a placeholder - you'll need to implement based on your needs
            
            messages.success(request, 'Cart saved for later')
            return redirect('wishlist')  # Redirect to wishlist page
            
        except Exception as e:
            messages.error(request, f'Error saving cart: {str(e)}')
            return redirect('cart')
    
    return redirect('cart')


def get_cart_summary(request):
    """Get cart summary for mini-cart display"""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            cart = get_or_create_cart(request)
            items = cart.items.select_related('product')[:5]  # Limit to 5 items
            
            # Calculate totals
            subtotal = float(cart.total_price)
            tax = subtotal * 0.1  # 10% tax
            discount = 0.0
            
            # Check for applied promo code in session
            applied_promo = request.session.get('applied_promo')
            if applied_promo:
                discount = applied_promo.get('discount', 0.0)
            
            # Determine shipping cost
            shipping = 0.0 if subtotal > 50 else 5.99
            
            # Calculate grand total
            grand_total = subtotal + tax + shipping - discount
            
            cart_data = {
                'total': subtotal,
                'quantity': cart.total_quantity,
                'tax': tax,
                'discount': discount,
                'shipping': shipping,
                'grand_total': grand_total,
                'items': [
                    {
                        'id': item.id,
                        'product_id': item.product.id,
                        'name': item.product.name,
                        'quantity': item.quantity,
                        'price': float(item.price),
                        'total': float(item.total_price),
                        'image_url': item.product.get_image_url(),
                        'url': item.product.get_absolute_url(),
                    }
                    for item in items
                ]
            }
            
            return JsonResponse({
                'success': True,
                'cart': cart_data
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })
    
    return JsonResponse({'success': False, 'error': 'Invalid request'})