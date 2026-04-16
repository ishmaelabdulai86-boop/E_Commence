# apps/cart/urls.py
from django.urls import path
from . import views

app_name = 'cart'

urlpatterns = [
    path('', views.cart_view, name='cart'),
    path('add/<int:product_id>/', views.add_to_cart, name='add_to_cart'),
    path('update/<int:item_id>/', views.update_cart_item, name='update_cart_item'),
    path('remove/<int:item_id>/', views.remove_from_cart, name='remove_from_cart'),
    path('clear/', views.clear_cart, name='clear_cart'),
    path('apply-promo/<str:code>/', views.apply_promo_code, name='apply_promo_code'),
    path('remove-promo/', views.remove_promo_code, name='remove_promo_code'),
    path('save-later/', views.save_cart_for_later, name='save_cart_for_later'),
    path('summary/', views.get_cart_summary, name='cart_summary'),
]