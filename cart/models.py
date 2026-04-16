# apps/cart/models.py
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal

class Cart(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='carts'
    )
    session_key = models.CharField(max_length=40, null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'session_key'],
                name='unique_user_session_cart'
            )
        ]
        indexes = [
            models.Index(fields=['user', 'session_key']),
            models.Index(fields=['updated_at']),
        ]
    
    @property
    def total_price(self):
        """Calculate total price of all items in cart using Decimal for precision"""
        total = Decimal('0')
        for item in self.items.all():
            total += Decimal(str(item.total_price))
        return total.quantize(Decimal('0.01'))
    
    @property
    def total_quantity(self):
        """Calculate total quantity of all items in cart"""
        return sum(item.quantity for item in self.items.all())
    
    @property
    def subtotal(self):
        """Subtotal before discounts and taxes"""
        return self.total_price
    
    def get_total_after_discounts(self, discount_amount=0):
        """Calculate total after applying discounts"""
        total = self.total_price
        return max(0, total - discount_amount)
    
    def clear(self):
        """Remove all items from cart"""
        self.items.all().delete()
        self.save()
    
    def merge_with_session_cart(self, session_cart):
        """Merge session cart with user cart when user logs in"""
        if session_cart and session_cart != self:
            for item in session_cart.items.all():
                try:
                    existing_item = self.items.get(product=item.product)
                    # Add quantities, but don't exceed product stock
                    new_quantity = min(
                        existing_item.quantity + item.quantity,
                        item.product.stock
                    )
                    existing_item.quantity = new_quantity
                    # Update to current price to ensure correlation
                    existing_item.price = item.product.discount_price or item.product.price
                    existing_item.save()
                except CartItem.DoesNotExist:
                    # Create new item in user's cart with current price
                    current_price = item.product.discount_price or item.product.price
                    CartItem.objects.create(
                        cart=self,
                        product=item.product,
                        quantity=min(item.quantity, item.product.stock),
                        price=current_price
                    )
            # Delete the session cart
            session_cart.delete()
    
    def __str__(self):
        if self.user:
            return f"Cart for {self.user.username} (ID: {self.id})"
        return f"Cart {self.session_key} (ID: {self.id})"


class CartItem(models.Model):
    cart = models.ForeignKey(
        Cart, 
        on_delete=models.CASCADE, 
        related_name='items'
    )
    product = models.ForeignKey(
        'products.Product', 
        on_delete=models.CASCADE,
        related_name='cart_items'
    )
    quantity = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)]
    )
    price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Price at the time of adding to cart"
    )
    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['cart', 'product'],
                name='unique_product_in_cart'
            )
        ]
        indexes = [
            models.Index(fields=['cart', 'product']),
            models.Index(fields=['added_at']),
        ]
        ordering = ['-added_at']
    
    @property
    def total_price(self):
        """Calculate total price for this item using Decimal for precision"""
        price_decimal = Decimal(str(self.price))
        return (price_decimal * Decimal(self.quantity)).quantize(Decimal('0.01'))
    
    @property
    def is_available(self):
        """Check if product is still available and in stock"""
        return self.product.is_active and self.quantity <= self.product.stock
    
    def update_price_if_needed(self):
        """Update price if product price has changed"""
        current_price = self.product.discount_price or self.product.price
        if self.price != current_price:
            self.price = current_price
            self.save()
        return self
    
    def __str__(self):
        return f"{self.quantity} × {self.product.name} (${self.price})"