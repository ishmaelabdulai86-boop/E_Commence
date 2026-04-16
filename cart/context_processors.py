# apps/cart/context_processors.py
from .models import Cart

def cart_items_count(request):
    cart_count = 0
    cart_total = 0
    
    try:
        if request.user.is_authenticated:
            cart = Cart.objects.filter(user=request.user, is_active=True).first()
        else:
            session_key = request.session.session_key
            if session_key:
                cart = Cart.objects.filter(session_key=session_key, user=None, is_active=True).first()
            else:
                cart = None
        
        if cart:
            cart_count = cart.total_quantity
            cart_total = cart.total_price
    
    except Exception:
        # Gracefully handle any errors
        pass
    
    return {
        'cart_items_count': cart_count,
        'cart_total_amount': cart_total,
    }