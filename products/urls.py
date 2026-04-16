# products/urls.py
from django.urls import path
from . import views

app_name = 'products'

urlpatterns = [
    # ==================== PRODUCT ADMIN URLS (MUST BE FIRST!) ====================
    # All admin/manage paths must come BEFORE any catch-all patterns
    path('manage/products/', views.admin_product_list, name='admin_product_list'),
    path('manage/products/create/', views.admin_product_create, name='admin_product_create'),
    path('manage/products/<int:pk>/', views.admin_product_detail, name='admin_product_detail'),
    path('manage/products/<int:pk>/edit/', views.admin_product_edit, name='admin_product_edit'),
    path('manage/products/<int:pk>/delete/', views.admin_product_delete, name='admin_product_delete'),
    path('manage/products/<int:pk>/images/', views.admin_product_images, name='admin_product_images'),
    
    path('manage/categories/', views.admin_category_list, name='admin_category_list'),
    path('manage/categories/create/', views.admin_category_create, name='admin_category_create'),
    path('manage/categories/<int:pk>/', views.admin_category_detail, name='admin_category_detail'),
    path('manage/categories/<int:pk>/edit/', views.admin_category_edit, name='admin_category_edit'),
    path('manage/categories/<int:pk>/delete/', views.admin_category_delete, name='admin_category_delete'),
    
    path('manage/reviews/', views.admin_review_list, name='admin_review_list'),
    path('manage/reviews/<int:pk>/approve/', views.admin_review_approve, name='admin_review_approve'),
    path('manage/reviews/<int:pk>/delete/', views.admin_review_delete, name='admin_review_delete'),
    
    path('manage/images/<int:image_id>/delete/', views.admin_product_image_delete, name='admin_product_image_delete'),
    path('manage/images/<int:image_id>/set-primary/', views.admin_product_image_set_primary, name='admin_product_image_set_primary'),
    
    # ==================== PUBLIC URLS (SPECIFIC PATHS BEFORE CATCH-ALL) ====================
    path('wishlist/', views.wishlist_view, name='wishlist'),
    path('wishlist/add/<int:product_id>/', views.add_to_wishlist, name='add_to_wishlist'),
    path('wishlist/remove/<int:product_id>/', views.remove_from_wishlist, name='remove_from_wishlist'),
    path('wishlist/toggle/<int:product_id>/', views.toggle_wishlist, name='toggle_wishlist'),
    path('wishlist/check/<int:product_id>/', views.check_wishlist, name='check_wishlist'),
    path('wishlist/move-all-to-cart/', views.move_all_to_cart, name='move_all_to_cart'),
    path('wishlist/clear/', views.clear_wishlist, name='clear_wishlist'),
    
    path('compare/add/<int:product_id>/', views.add_to_comparison, name='add_to_comparison'),
    
    path('category/', views.category_list, name='category_list'),
    path('category/<slug:category_slug>/products/', views.product_list, name='product_list_by_category'),
    path('category/<slug:slug>/', views.category_detail, name='category_detail'),
    path('search/', views.product_search, name='product_search'),
    path('review/<int:product_id>/', views.add_review, name='add_review'),
    
    # ==================== CATCH-ALL (MUST BE LAST!) ====================
    # This catches any slug that hasn't matched previous patterns
    path('', views.product_list, name='product_list'),
    path('<slug:product_slug>/', views.product_detail, name='product_detail'),
]