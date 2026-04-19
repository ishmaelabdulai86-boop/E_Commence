from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Avg, Count
from django.core.paginator import Paginator
from django_ratelimit.decorators import ratelimit
from django.http import JsonResponse, HttpResponse
import json
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum, Count, Avg, Q, F, Max
from .models import Product, Category, ProductReview, Wishlist
from .utils import update_product_rating, get_low_stock_count, get_pending_reviews_count
from django.contrib.auth.models import User
from django.db import models
from .forms import ProductForm, ProductEditForm, CategoryForm, ProductImage, ProductSpecification, ProductImageFormSet, ProductSpecificationFormSet, ProductImageFormSetEdit, ProductSpecificationFormSetEdit
# products/views.py
from django.shortcuts import render, get_object_or_404
from django.db.models import Q, Count, Avg
from django.core.paginator import Paginator
from .models import Category, Product, ProductReview, Wishlist, ProductImage, ProductSpecification
from orders.models import Order


def is_admin_or_seller(user):
    """Check if user is admin or seller"""
    return user.is_authenticated and (user.is_staff or user.role in ['admin', 'seller'])


def home_view(request):
    """Home page view with role-based redirect"""
    # If user is logged in and is an admin/seller, redirect to admin dashboard
    if request.user.is_authenticated and (request.user.is_staff or getattr(request.user, 'role', None) in ['admin', 'seller']):
        return redirect('analytics:analytics_dashboard')
    
    # Otherwise render home page
    return render(request, 'home.html')


def category_list(request):
    """Display all active categories"""
    categories = Category.objects.filter(
        parent__isnull=True,  # Only top-level categories
        is_active=True
    ).annotate(
        product_count=Count('products'),
        subcategory_count=Count('children')
    ).prefetch_related('children').order_by('name')
    
    # Get total count of top-level categories
    total_categories = categories.count()
    
    # You can add pagination here if needed
    paginator = Paginator(categories, 12)
    page = request.GET.get('page')
    categories = paginator.get_page(page)
    
    context = {
        'categories': categories,
        'total_categories': total_categories,  # Add this line!
    }
    
    return render(request, 'products/category_list.html', context)

def category_detail(request, slug):
    """Display products in a specific category"""
    category = get_object_or_404(Category, slug=slug, is_active=True)
    
    # Get products in this category (including subcategories if needed)
    products = Product.objects.filter(
        category=category,
        is_active=True
    ).select_related('category').prefetch_related('images', 'reviews')
    
    # Apply filters
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    in_stock = request.GET.get('in_stock')
    out_of_stock = request.GET.get('out_of_stock')
    featured = request.GET.get('featured')
    on_sale = request.GET.get('on_sale')
    min_rating = request.GET.get('min_rating')
    sort_by = request.GET.get('sort')
    search_query = request.GET.get('q', '')
    
    # Price filter
    if min_price:
        try:
            products = products.filter(price__gte=float(min_price))
        except ValueError:
            pass
    if max_price:
        try:
            products = products.filter(price__lte=float(max_price))
        except ValueError:
            pass
    
    # Availability filter
    if in_stock == 'true':
        products = products.filter(stock__gt=0)
    elif out_of_stock == 'true':
        products = products.filter(stock=0)
    
    # Featured filter
    if featured == 'true':
        products = products.filter(is_featured=True)
    
    # On sale filter
    if on_sale == 'true':
        products = products.filter(is_on_sale=True, discount_price__isnull=False)
    
    # Rating filter
    if min_rating:
        try:
            min_rating_float = float(min_rating)
            products = products.filter(rating__gte=min_rating_float)
        except ValueError:
            pass
    
    # Search filter
    if search_query:
        products = products.filter(
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(sku__icontains=search_query) |
            Q(full_description__icontains=search_query)
        )
    max_price_value = products.aggregate(Max('price'))['price__max'] or 1000
    # Sorting
    sort_options = {
        'popularity': '-sold_count',
        'price_low_high': 'price',
        'price_high_low': '-price',
        'newest': '-created_at',
        'rating': '-rating',
        'name_asc': 'name',
        'name_desc': '-name',
        'bestsellers': '-sold_count',
    }
    
    if sort_by in sort_options:
        products = products.order_by(sort_options[sort_by])
    else:
        products = products.order_by('-created_at')
    
    # Pagination
    paginator = Paginator(products, 12)  # Show 12 products per page
    page = request.GET.get('page')
    products = paginator.get_page(page)
    
    # Get subcategories
    subcategories = Category.objects.filter(
        parent=category,
        is_active=True
    ).annotate(product_count=Count('products')).order_by('name')
    
    # Get related categories (same parent or similar)
    related_categories = Category.objects.filter(
        parent=category.parent,
        is_active=True
    ).exclude(id=category.id).annotate(
        product_count=Count('products')
    ).order_by('?')[:4]  # Random 4 related categories
    
    context = {
        'category': category,
        'products': products,
        'subcategories': subcategories,
        'related_categories': related_categories,
        'total_products': paginator.count,
        'max_price': max_price_value,
    }
    
    return render(request, 'products/category.html', context)

def product_list(request, category_slug=None):
    """Product listing page with filtering"""
    category = None
    categories = Category.objects.filter(is_active=True, parent=None)
    products = Product.objects.filter(is_active=True).select_related('category')
    
    if category_slug:
        category = get_object_or_404(Category, slug=category_slug, is_active=True)
        products = products.filter(category=category)
    
    # ANNOTATE products with review count only (no average rating)
    products = products.annotate(
        total_reviews=Count('reviews', filter=models.Q(reviews__is_approved=True))
    )
    
    # Filtering
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    sort_by = request.GET.get('sort_by', 'newest')
    availability = request.GET.get('availability')
    min_rating = request.GET.get('min_rating')
    categories_filter = request.GET.get('categories', '')
    
    # Price filter
    if min_price:
        try:
            products = products.filter(price__gte=float(min_price))
        except ValueError:
            pass
    
    if max_price:
        try:
            products = products.filter(price__lte=float(max_price))
        except ValueError:
            pass
    
    # Availability filter
    if availability == 'in_stock':
        products = products.filter(stock__gt=0)
    elif availability == 'out_of_stock':
        products = products.filter(stock=0)
    
    # Rating filter - using the product's rating field
    if min_rating:
        try:
            min_rating = float(min_rating)
            products = products.filter(rating__gte=min_rating)
        except ValueError:
            pass
    
    # Category filter
    if categories_filter:
        category_ids = [int(cid) for cid in categories_filter.split(',') if cid.isdigit()]
        if category_ids:
            products = products.filter(category_id__in=category_ids)
    
    # Sorting
    if sort_by == 'price_low':
        products = products.order_by('price')
    elif sort_by == 'price_high':
        products = products.order_by('-price')
    elif sort_by == 'popular':
        products = products.order_by('-sold_count')
    elif sort_by == 'rating':
        products = products.order_by('-rating')  # Use product's rating field
    elif sort_by == 'name':
        products = products.order_by('name')
    else:  # newest
        products = products.order_by('-created_at')
    
    # Get product count for each category
    for cat in categories:
        cat.product_count = Product.objects.filter(category=cat, is_active=True).count()
    
    # Pagination
    paginator = Paginator(products, 12)
    page = request.GET.get('page')
    products = paginator.get_page(page)
    
    # Set the review_count for each product from annotation
    for product in products:
        product.review_count = getattr(product, 'total_reviews', 0)
    
    context = {
        'category': category,
        'categories': categories,
        'products': products,
        'sort_by': sort_by,
        'min_price': min_price or '',
        'max_price': max_price or '',
        'products_count': paginator.count,
    }
    
    return render(request, 'products/list.html', context)

def product_search(request):
    """Search products"""
    query = request.GET.get('q', '')
    
    if query:
        # Search in name, description, and SKU
        products = Product.objects.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(sku__icontains=query) |
            Q(category__name__icontains=query),
            is_active=True
        ).distinct()
    else:
        products = Product.objects.filter(is_active=True)
    
    # Apply filters from request
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    
    if min_price:
        try:
            products = products.filter(price__gte=float(min_price))
        except ValueError:
            pass
    
    if max_price:
        try:
            products = products.filter(price__lte=float(max_price))
        except ValueError:
            pass
    
    # Get categories for filter sidebar
    categories = Category.objects.filter(is_active=True, parent=None)
    
    # Pagination
    paginator = Paginator(products, 12)
    page = request.GET.get('page')
    products = paginator.get_page(page)
    
    context = {
        'products': products,
        'query': query,
        'categories': categories,
        'products_count': paginator.count,
    }
    
    return render(request, 'products/search.html', context)

def product_detail(request, product_slug):
    """Product detail page"""
    try:
        product = Product.objects.select_related('category').prefetch_related(
            'images', 'reviews'
        ).get(slug=product_slug, is_active=True)
    except Product.DoesNotExist:
        return render(request, '404.html', {'message': 'Product not found'}, status=404)
    
    # Calculate review statistics
    approved_reviews = product.reviews.filter(is_approved=True)
    review_count = approved_reviews.count()
    
    
    # Attach calculated values to product object
    product.review_count = review_count
    
    
    # Track recently viewed
    if 'recently_viewed' in request.session:
        if product.id in request.session['recently_viewed']:
            request.session['recently_viewed'].remove(product.id)
        request.session['recently_viewed'].insert(0, product.id)
        if len(request.session['recently_viewed']) > 5:
            request.session['recently_viewed'] = request.session['recently_viewed'][:5]
    else:
        request.session['recently_viewed'] = [product.id]
    request.session.modified = True
    
    # Get related products (same category) - prefetch images for performance
    related_products = Product.objects.filter(
        category=product.category,
        is_active=True
    ).exclude(id=product.id).prefetch_related('images')[:4]
    
    # Add review count and rating to related products
    for related in related_products:
        related_reviews = related.reviews.filter(is_approved=True)
        related.review_count = related_reviews.count()
        
    
    # Get rating distribution
    rating_distribution = approved_reviews.values('rating').annotate(count=Count('id')).order_by('-rating')
    
    # Prepare rating counts for template
    rating_counts = {i: 0 for i in range(1, 6)}
    for rd in rating_distribution:
        rating_counts[rd['rating']] = rd['count']
    
    context = {
        'product': product,
        'related_products': related_products if related_products.exists() else [],
        'rating_counts': rating_counts,
        'review_count': review_count,
    }
    
    return render(request, 'products/detail.html', context)

@login_required
@ratelimit(key='user', rate='5/m')
def add_review(request, product_id):
    """Add or update product review"""
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id, is_active=True)
        title = request.POST.get('title', '')
        rating = request.POST.get('rating')
        comment = request.POST.get('comment')
        
        # Check for AJAX request
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if not rating or not comment:
            if is_ajax:
                return JsonResponse({
                    'success': False, 
                    'message': 'Rating and comment are required.'
                })
            messages.error(request, 'Rating and comment are required.')
            return redirect('products:product_detail', product_slug=product.slug)
        
        try:
            rating = int(rating)
            if rating < 1 or rating > 5:
                raise ValueError
        except ValueError:
            if is_ajax:
                return JsonResponse({'success': False, 'message': 'Invalid rating value.'})
            messages.error(request, 'Invalid rating value.')
            return redirect('products:product_detail', product_slug=product.slug)
        
        # Check if user has already reviewed
        existing_review = ProductReview.objects.filter(
            user=request.user, 
            product=product
        ).first()
        
        if existing_review:
            # Update existing review
            existing_review.rating = rating
            existing_review.comment = comment
            existing_review.title = title
            existing_review.save()
            message = 'Review updated successfully.'
            if is_ajax:
                # Call update_product_rating here
                update_product_rating(product)
                return JsonResponse({'success': True, 'message': message})
            messages.info(request, message)
        else:
            # Create new review
            ProductReview.objects.create(
                user=request.user,
                title=title,
                product=product,
                rating=rating,
                comment=comment,
                is_approved=True
            )
            message = 'Review added successfully.'
            if is_ajax:
                # Call update_product_rating here
                update_product_rating(product)
                return JsonResponse({'success': True, 'message': message})
            messages.success(request, message)
        
        # Update product rating for non-AJAX requests
        update_product_rating(product)
        
        # Redirect for non-AJAX requests
        return redirect('products:product_detail', product_slug=product.slug)
    
    # If GET request, redirect to product detail
    return redirect('products:product_detail', product_slug=product.slug)


@login_required
def wishlist_view(request):
    """View user wishlist"""
    wishlist_items = Wishlist.objects.filter(user=request.user).select_related('product')
    
    context = {
        'wishlist_items': wishlist_items,
    }
    
    return render(request, 'products/wishlist.html', context)

@login_required
@ratelimit(key='user', rate='10/m')
def add_to_wishlist(request, product_id):
    """Add product to wishlist"""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            product = Product.objects.get(id=product_id, is_active=True)
            wishlist_item, created = Wishlist.objects.get_or_create(
                user=request.user,
                product=product
            )
            
            if created:
                return JsonResponse({'success': True, 'action': 'added', 'message': 'Added to wishlist'})
            else:
                return JsonResponse({'success': False, 'message': 'Already in wishlist'})
        
        except Product.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Product not found'})
    
    return JsonResponse({'success': False, 'message': 'Invalid request'})

@login_required
@ratelimit(key='user', rate='10/m')
def remove_from_wishlist(request, product_id):
    """Remove product from wishlist"""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            wishlist_item = Wishlist.objects.get(
                user=request.user,
                product_id=product_id
            )
            wishlist_item.delete()
            
            return JsonResponse({'success': True, 'action': 'removed', 'message': 'Removed from wishlist'})
        
        except Wishlist.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Item not in wishlist'})
    
    return JsonResponse({'success': False, 'message': 'Invalid request'})

@login_required
@ratelimit(key='user', rate='10/m')
def toggle_wishlist(request, product_id):
    """Toggle product in wishlist"""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            product = Product.objects.get(id=product_id, is_active=True)
            wishlist_item, created = Wishlist.objects.get_or_create(
                user=request.user,
                product=product
            )
            
            if created:
                return JsonResponse({'success': True, 'action': 'added'})
            else:
                wishlist_item.delete()
                return JsonResponse({'success': True, 'action': 'removed'})
        
        except Product.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Product not found'})
    
    return JsonResponse({'success': False, 'message': 'Invalid request'})
    
@login_required
def check_wishlist(request, product_id):
    """Check if product is in wishlist"""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        in_wishlist = Wishlist.objects.filter(
            user=request.user,
            product_id=product_id
        ).exists()
        
        return JsonResponse({'in_wishlist': in_wishlist})
    
    return JsonResponse({'in_wishlist': False})

@login_required
@ratelimit(key='user', rate='5/m')
def move_all_to_cart(request):
    """Move all wishlist items to cart"""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        from cart.models import Cart, CartItem
        
        try:
            cart, created = Cart.objects.get_or_create(user=request.user)
            wishlist_items = Wishlist.objects.filter(user=request.user).select_related('product')
            
            for item in wishlist_items:
                if item.product.stock > 0:
                    cart_item, item_created = CartItem.objects.get_or_create(
                        cart=cart,
                        product=item.product,
                        defaults={'price': item.product.discount_price or item.product.price}
                    )
                    
                    if not item_created and cart_item.quantity + 1 <= item.product.stock:
                        cart_item.quantity += 1
                        cart_item.save()
            
            # Clear wishlist after moving to cart
            wishlist_items.delete()
            
            return JsonResponse({'success': True, 'message': 'All items moved to cart'})
        
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    
    return JsonResponse({'success': False, 'message': 'Invalid request'})

@login_required
@ratelimit(key='user', rate='5/m')
def clear_wishlist(request):
    """Clear all items from wishlist"""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            Wishlist.objects.filter(user=request.user).delete()
            return JsonResponse({'success': True, 'message': 'Wishlist cleared'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    
    return JsonResponse({'success': False, 'message': 'Invalid request'})

def update_product_rating(product):
    """Update product average rating"""
    reviews = ProductReview.objects.filter(product=product, is_approved=True)
    avg_rating = reviews.aggregate(Avg('rating'))['rating__avg'] or 0
    review_count = reviews.count()
    
    product.rating = round(avg_rating, 2)
    product.review_count = review_count
    product.save()

# Additional utility view for product comparison
@login_required
def add_to_comparison(request, product_id):
    """Add product to comparison list"""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        if 'comparison_list' not in request.session:
            request.session['comparison_list'] = []
        
        if product_id not in request.session['comparison_list']:
            if len(request.session['comparison_list']) >= 4:  # Limit to 4 products
                return JsonResponse({'success': False, 'message': 'Comparison list is full (max 4 products)'})
            
            request.session['comparison_list'].append(product_id)
            request.session.modified = True
            return JsonResponse({'success': True, 'message': 'Added to comparison'})
        else:
            return JsonResponse({'success': False, 'message': 'Already in comparison list'})
    
    return JsonResponse({'success': False, 'message': 'Invalid request'})


def update_product_rating(product):
    """Update product's average rating and review count"""
    from django.db.models import Avg
    
    # Get all approved reviews for this product
    reviews = ProductReview.objects.filter(product=product, is_approved=True)
    
    if reviews.exists():
        # Calculate average rating
        avg_rating = reviews.aggregate(Avg('rating'))['rating__avg']
        review_count = reviews.count()
        
        # Update the product
        product.rating = round(avg_rating, 2)
        product.review_count = review_count
        
        # Force save to database
        product.save(update_fields=['rating', 'review_count'])
        
    else:
        # No reviews, reset to 0
        product.rating = 0
        product.review_count = 0
        product.save(update_fields=['rating', 'review_count'])
                
        
def get_low_stock_count():
    """Get count of products with low stock"""
    return Product.objects.filter(stock__lte=models.F('low_stock_threshold'), stock__gt=0).count()

def get_pending_reviews_count():
    """Get count of pending reviews"""
    return ProductReview.objects.filter(is_approved=False).count()

# ==================== ADMIN VIEWS ====================

def is_admin_or_seller(user):
    """Check if user is admin or seller"""
    return user.is_authenticated and (user.is_staff or user.role in ['admin', 'seller'])

@login_required
@user_passes_test(is_admin_or_seller)
def admin_dashboard(request):
    """Admin dashboard view"""
    # Get stats for dashboard
    total_products = Product.objects.count()
    total_orders = Order.objects.count()
    total_users = User.objects.count()
    
    # Recent orders
    recent_orders = Order.objects.order_by('-created_at')[:5]
    
    # Low stock products
    low_stock_products = Product.objects.filter(
        stock__lte=models.F('low_stock_threshold'),
        stock__gt=0
    )[:5]
    
    # Pending reviews
    pending_reviews = ProductReview.objects.filter(is_approved=False)[:5]
    
    context = {
        'total_products': total_products,
        'total_orders': total_orders,
        'total_users': total_users,
        'recent_orders': recent_orders,
        'low_stock_products': low_stock_products,
        'pending_reviews': pending_reviews,
    }
    
    return render(request, 'products/admin_dashboard.html', context)

@login_required
@user_passes_test(is_admin_or_seller)
def admin_product_list(request):
    """Admin product listing with filters"""
    products = Product.objects.all().select_related('category')
    
    # Apply filters
    search_query = request.GET.get('q', '')
    category_filter = request.GET.get('category', '')
    status_filter = request.GET.get('status', '')
    stock_filter = request.GET.get('stock', '')
    
    if search_query:
        products = products.filter(
            Q(name__icontains=search_query) |
            Q(sku__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    if category_filter:
        products = products.filter(category_id=category_filter)
    
    if status_filter:
        if status_filter == 'active':
            products = products.filter(is_active=True)
        elif status_filter == 'inactive':
            products = products.filter(is_active=False)
    
    if stock_filter:
        if stock_filter == 'low':
            products = products.filter(stock__lte=models.F('low_stock_threshold'))
        elif stock_filter == 'out':
            products = products.filter(stock=0)
    
    # Get stats
    total_products = Product.objects.count()
    active_products = Product.objects.filter(is_active=True).count()
    low_stock = Product.objects.filter(stock__lte=models.F('low_stock_threshold')).count()
    out_of_stock = Product.objects.filter(stock=0).count()
    
    # Get categories for filter
    categories = Category.objects.all()
    
    # Pagination
    paginator = Paginator(products.order_by('-created_at'), 20)
    page = request.GET.get('page')
    products = paginator.get_page(page)
    
    # Preserve query parameters for pagination
    query_params = request.GET.copy()
    if 'page' in query_params:
        del query_params['page']
    
    context = {
        'products': products,
        'categories': categories,
        'total_products': total_products,
        'active_products': active_products,
        'low_stock_count': low_stock,
        'out_of_stock': out_of_stock,
        'query_params': query_params.urlencode(),
    }
    
    return render(request, 'admin/products/admin_list.html', context)

@login_required
@user_passes_test(is_admin_or_seller)
def admin_product_detail(request, pk):
    """Admin product detail view"""
    product = get_object_or_404(Product.objects.prefetch_related('images', 'specifications'), id=pk)
    reviews = product.reviews.all().select_related('user')
    
    context = {
        'product': product,
        'reviews': reviews,
    }
    
    return render(request, 'admin/products/admin_detail.html', context)

@login_required
@user_passes_test(is_admin_or_seller)
@login_required
@user_passes_test(is_admin_or_seller)
def admin_product_create(request):
    """Create new product with images and specifications"""
    if request.method == 'POST':
        form = ProductForm(request.POST)
        image_formset = ProductImageFormSet(request.POST, request.FILES, prefix='images')
        spec_formset = ProductSpecificationFormSet(request.POST, prefix='specs')
        
        # Check if main form is valid
        if form.is_valid():
            product = form.save()
            
            # Validate formsets (they should always be valid with our custom classes)
            image_formset.is_valid()
            spec_formset.is_valid()
            
            # Process images - only save those with actual images
            for image_form in image_formset.forms:
                try:
                    # Skip if form is marked for deletion
                    if image_form.cleaned_data.get('DELETE', False):
                        continue
                    
                    # Only process if image file exists
                    image_file = image_form.cleaned_data.get('image')
                    if image_file:
                        image = image_form.save(commit=False)
                        image.product = product
                        image.save()
                except Exception as e:
                    # Skip forms with issues (empty forms)
                    pass
            
            # Process specifications - only save those with both key and value
            for spec_form in spec_formset.forms:
                try:
                    # Skip if form is marked for deletion
                    if spec_form.cleaned_data.get('DELETE', False):
                        continue
                    
                    key = spec_form.cleaned_data.get('key', '').strip()
                    value = spec_form.cleaned_data.get('value', '').strip()
                    if key and value:
                        spec = spec_form.save(commit=False)
                        spec.product = product
                        spec.save()
                except Exception as e:
                    # Skip forms with issues (empty forms)
                    pass
            
            messages.success(request, f'Product "{product.name}" created successfully!')
            return redirect('products:admin_product_list')
        else:
            # Display form errors
            for field, error_list in form.errors.items():
                for error in error_list:
                    messages.error(request, f'{field}: {error}')
    else:
        form = ProductForm()
        image_formset = ProductImageFormSet(prefix='images')
        spec_formset = ProductSpecificationFormSet(prefix='specs')
    
    context = {
        'form': form,
        'image_formset': image_formset,
        'spec_formset': spec_formset,
        'title': 'Create New Product',
    }
    
    return render(request, 'admin/products/admin_form_create.html', context)


@login_required
@user_passes_test(is_admin_or_seller)
def admin_product_edit(request, pk):
    """Edit existing product with images and specifications"""
    product = get_object_or_404(Product, id=pk)
    
    if request.method == 'POST':
        form = ProductEditForm(request.POST, instance=product)
        image_formset = ProductImageFormSetEdit(request.POST, request.FILES, instance=product, prefix='images')
        spec_formset = ProductSpecificationFormSetEdit(request.POST, instance=product, prefix='specs')
        
        # Check if main form is valid
        if form.is_valid():
            product = form.save()
            
            # Validate formsets
            image_formset.is_valid()
            spec_formset.is_valid()
            
            # Process images
            for image_form in image_formset.forms:
                try:
                    # Check if this form is marked for deletion
                    if image_form.cleaned_data.get('DELETE', False):
                        if image_form.instance.pk:
                            image_form.instance.delete()
                        continue
                    
                    # Check if this is a new image with file
                    image_file = image_form.cleaned_data.get('image')
                    if image_file:
                        image = image_form.save(commit=False)
                        image.product = product
                        image.save()
                except Exception as e:
                    # Skip empty forms with no data
                    pass
            
            # Process specifications
            for spec_form in spec_formset.forms:
                try:
                    # Check if this form is marked for deletion
                    if spec_form.cleaned_data.get('DELETE', False):
                        if spec_form.instance.pk:
                            spec_form.instance.delete()
                        continue
                    
                    # Check if this is a new specification with key and value
                    key = spec_form.cleaned_data.get('key', '').strip()
                    value = spec_form.cleaned_data.get('value', '').strip()
                    if key and value:
                        spec = spec_form.save(commit=False)
                        spec.product = product
                        spec.save()
                except Exception as e:
                    # Skip empty forms with no data
                    pass
            
            messages.success(request, f'Product "{product.name}" updated successfully!')
            return redirect('products:admin_product_list')
        else:
            # Display form errors
            for field, error_list in form.errors.items():
                for error in error_list:
                    messages.error(request, f'{field}: {error}')
    else:
        form = ProductEditForm(instance=product)
        image_formset = ProductImageFormSetEdit(instance=product, prefix='images')
        spec_formset = ProductSpecificationFormSetEdit(instance=product, prefix='specs')
    
    context = {
        'form': form,
        'image_formset': image_formset,
        'spec_formset': spec_formset,
        'title': f'Edit Product: {product.name}',
        'product': product,
    }
    
    return render(request, 'admin/products/admin_edit.html', context)

@login_required
@user_passes_test(is_admin_or_seller)
def admin_product_delete(request, pk):
    """Delete product"""
    product = get_object_or_404(Product, id=pk)
    
    if request.method == 'POST':
        product_name = product.name
        product.delete()
        messages.success(request, f'Product "{product_name}" deleted successfully!')
        return redirect('products:admin_product_list')
    
    return render(request, 'admin/products/admin_confirm_delete.html', {'product': product})

# Category Management Views
@login_required
@user_passes_test(is_admin_or_seller)
def admin_category_list(request):
    """Admin category listing with filters"""
    categories = Category.objects.all().prefetch_related('children', 'products')
    
    # Search
    search_query = request.GET.get('q', '')
    if search_query:
        categories = categories.filter(
            Q(name__icontains=search_query) | 
            Q(description__icontains=search_query)
        )
    
    # Filter by status
    status = request.GET.get('status')
    if status == 'active':
        categories = categories.filter(is_active=True)
    elif status == 'inactive':
        categories = categories.filter(is_active=False)
    
    # Filter by type (main or subcategories)
    cat_type = request.GET.get('type')
    if cat_type == 'main':
        categories = categories.filter(parent__isnull=True)
    elif cat_type == 'sub':
        categories = categories.filter(parent__isnull=False)
    
    # Calculate stats
    all_categories = Category.objects.all()
    total_categories = all_categories.count()
    active_categories = all_categories.filter(is_active=True).count()
    total_subcategories = all_categories.filter(parent__isnull=False).count()
    total_products = Product.objects.count()
    
    context = {
        'categories': categories,
        'total_categories': total_categories,
        'active_categories': active_categories,
        'total_subcategories': total_subcategories,
        'total_products': total_products,
    }
    
    return render(request, 'admin/products/admin_category_list.html', context)

@login_required
@user_passes_test(is_admin_or_seller)
def admin_category_create(request):
    """Create new category"""
    if request.method == 'POST':
        form = CategoryForm(request.POST, request.FILES)
        if form.is_valid():
            category = form.save()
            messages.success(request, f'Category "{category.name}" created successfully!')
            return redirect('products:admin_category_list')
    else:
        form = CategoryForm()
    
    context = {
        'form': form,
        'title': 'Create New Category',
    }
    
    return render(request, 'admin/products/admin_category_form_create.html', context)

@login_required
@user_passes_test(is_admin_or_seller)
def admin_category_edit(request, pk):
    """Edit category"""
    category = get_object_or_404(Category, id=pk)
    
    if request.method == 'POST':
        form = CategoryForm(request.POST, request.FILES, instance=category)
        if form.is_valid():
            category = form.save()
            messages.success(request, f'Category "{category.name}" updated successfully!')
            return redirect('products:admin_category_list')
    else:
        form = CategoryForm(instance=category)
    
    context = {
        'form': form,
        'title': f'Edit Category: {category.name}',
        'category': category,
    }
    
    return render(request, 'admin/products/admin_category_edit.html', context)

@login_required
@user_passes_test(is_admin_or_seller)
def admin_category_delete(request, pk):
    """Delete category"""
    category = get_object_or_404(Category, id=pk)
    
    if request.method == 'POST':
        # Check if category can be deleted
        if category.products.exists() or category.children.exists():
            messages.error(request, 'Cannot delete category with products or subcategories.')
        else:
            category_name = category.name
            category.delete()
            messages.success(request, f'Category "{category_name}" deleted successfully!')
    
    return redirect('admin_category_list')
# Review Management Views
@login_required
@user_passes_test(is_admin_or_seller)
def admin_review_list(request):
    """Admin review listing with filters"""
    reviews = ProductReview.objects.all().select_related('product', 'user')
    
    # Apply filters
    status_filter = request.GET.get('status', '')
    rating_filter = request.GET.get('rating', '')
    
    if status_filter:
        if status_filter == 'approved':
            reviews = reviews.filter(is_approved=True)
        elif status_filter == 'pending':
            reviews = reviews.filter(is_approved=False)
    
    if rating_filter:
        reviews = reviews.filter(rating=rating_filter)
    
    # Get pending reviews count for sidebar
    pending_reviews = ProductReview.objects.filter(is_approved=False).count()
    
    # Pagination
    paginator = Paginator(reviews.order_by('-created_at'), 20)
    page = request.GET.get('page')
    reviews = paginator.get_page(page)
    
    context = {
        'reviews': reviews,
        'pending_reviews_count': pending_reviews,
    }
    
    return render(request, 'admin/products/admin_review_list.html', context)

@login_required
@user_passes_test(is_admin_or_seller)
def admin_review_approve(request, pk):
    """Approve a review"""
    review = get_object_or_404(ProductReview, id=pk)
    review.is_approved = True
    review.save()
    
    # Update product rating
    update_product_rating(review.product)
    
    messages.success(request, 'Review approved successfully!')
    return redirect('products:admin_review_list')

@login_required
@user_passes_test(is_admin_or_seller)
def admin_review_delete(request, pk):
    """Delete a review"""
    review = get_object_or_404(ProductReview, id=pk)
    product = review.product
    
    if request.method == 'POST':
        review.delete()
        
        # Update product rating
        update_product_rating(product)
        
        messages.success(request, 'Review deleted successfully!')
        return redirect('products:admin_review_list')
    
    return render(request, 'admin/products/admin_review_confirm_delete.html', {'review': review})

# categories/views.py or products/views.py
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import Category

def is_admin_or_staff(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)

@login_required
@user_passes_test(is_admin_or_staff)
def admin_category_detail(request, pk):
    """Admin category detail view"""
    category = get_object_or_404(Category, id=pk)
    
    # Calculate active products count
    active_products_count = category.products.filter(is_active=True).count()
    
    context = {
        'category': category,
        'active_products_count': active_products_count,
    }
    
    return render(request, 'admin/products/admin_category_detail.html', context)

# Add these to products/views.py

@login_required
@user_passes_test(is_admin_or_seller)
def admin_product_images(request, pk):
    """Manage product images"""
    product = get_object_or_404(Product, id=pk)
    
    if request.method == 'POST':
        images = request.FILES.getlist('images')
        for image in images:
            ProductImage.objects.create(
                product=product,
                image=image
            )
        messages.success(request, f'{len(images)} images uploaded successfully.')
        return redirect('products:admin_product_images', pk=product.id)
    
    images = product.images.all()
    
    context = {
        'product': product,
        'images': images,
    }
    
    return render(request, 'admin/products/admin_images.html', context)

@login_required
@user_passes_test(is_admin_or_seller)
def admin_product_image_set_primary(request, image_id):
    """Set image as primary via AJAX"""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            image = get_object_or_404(ProductImage, id=image_id)
            
            # Remove primary from other images
            image.product.images.update(is_primary=False)
            
            # Set this as primary
            image.is_primary = True
            image.save()
            
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    
    return JsonResponse({'success': False, 'message': 'Invalid request'})

@login_required
@user_passes_test(is_admin_or_seller)
def admin_product_image_delete(request, image_id):
    """Delete product image via AJAX"""
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            image = ProductImage.objects.get(id=image_id)
            product_id = image.product.id
            image.delete()
            return JsonResponse({'success': True, 'message': 'Image deleted'})
        except ProductImage.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Image not found'})
    return JsonResponse({'success': False, 'message': 'Invalid request'})