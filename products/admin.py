from django.contrib import admin
from .models import (
    Category, Product, ProductImage, ProductSpecification,
    ProductReview, Wishlist
)


class ProductImageInline(admin.StackedInline):
    model = ProductImage
    extra = 1


class ProductSpecificationInline(admin.TabularInline):
    model = ProductSpecification
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'sku', 'category', 'price', 'discount_price', 'stock', 'is_active', 'created_at']
    search_fields = ['name', 'sku', 'description']
    list_filter = ['is_active', 'is_featured', 'is_on_sale', 'category']
    inlines = [ProductImageInline, ProductSpecificationInline]
    readonly_fields = ['rating', 'review_count', 'sold_count', 'created_at', 'updated_at']


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'parent', 'is_active', 'image_preview']
    search_fields = ['name', 'slug']
    list_filter = ['is_active']
    
    def image_preview(self, obj):
        if obj.image:
            return f'<img src="{obj.image.url}" width="50" height="50" style="object-fit: cover;" />'
        return "No image"
    image_preview.allow_tags = True
    image_preview.short_description = "Image Preview"


@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = ['product', 'user', 'rating', 'is_approved', 'created_at']
    list_filter = ['is_approved', 'rating', 'created_at']
    search_fields = ['product__name', 'user__username', 'comment']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ['user', 'product', 'added_at']
    search_fields = ['user__username', 'product__name']
    readonly_fields = ['added_at']