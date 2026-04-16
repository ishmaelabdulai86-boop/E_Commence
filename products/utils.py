from django.db.models import Avg
from django.db import models


def update_product_rating(product):
    """Update product's average rating and review count"""
    # Calculate average rating from approved reviews
    reviews = product.reviews.filter(is_approved=True)
    
    if reviews.exists():
        avg_rating = reviews.aggregate(avg_rating=Avg('rating'))['avg_rating']
        review_count = reviews.count()
        
        product.rating = round(avg_rating, 2)
        product.review_count = review_count
        product.save(update_fields=['rating', 'review_count'])
    else:
        product.rating = 0
        product.review_count = 0
        product.save(update_fields=['rating', 'review_count'])


def get_low_stock_count():
    """Get count of products with low stock"""
    from .models import Product
    return Product.objects.filter(stock__lte=models.F('low_stock_threshold'), stock__gt=0).count()


def get_pending_reviews_count():
    """Get count of pending reviews"""
    from .models import ProductReview
    return ProductReview.objects.filter(is_approved=False).count()
