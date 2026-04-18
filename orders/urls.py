# orders/urls.py - Update
from django.urls import path
from . import views

app_name = 'orders'

urlpatterns = [
    # Public URLs
    path('', views.order_list, name='order_list'),
    path('checkout/', views.checkout, name='checkout'),
    path('checkout/process/', views.checkout_process, name='checkout_process'),
    path('success/<str:order_number>/', views.order_success, name='order_success'),
    path('<str:order_number>/', views.order_detail, name='order_detail'),
    path('<str:order_number>/cancel/', views.cancel_order, name='cancel_order'),
    path('<str:order_number>/track/', views.track_order, name='track_order'),
    path('<str:order_number>/invoice/', views.download_invoice, name='download_invoice'),
    path('<str:order_number>/return/<int:item_id>/', views.create_return_request, name='create_return_request'),
    path('create/', views.create_order, name='create_order'),
    
    path('api/order-details/<int:order_id>/', views.order_details_api, name='order_details_api'),
    # Redirect numeric IDs to order number URLs (legacy support)
    path('<int:order_id>/', views.order_id_redirect, name='order_id_redirect'),
    # Admin URLs
    path('manage/orders/', views.admin_order_list, name='admin_order_list'),
    path('manage/orders/<str:order_number>/', views.admin_order_detail, name='admin_order_detail'),
    path('manage/orders/<str:order_number>/update-status/', views.admin_update_order_status, name='admin_update_order_status'),
    path('manage/orders/<str:order_number>/update-payment-status/', views.admin_update_payment_status, name='admin_update_payment_status'),
    path('manage/returns/', views.admin_return_list, name='admin_return_list'),
    path('manage/returns/<int:return_id>/', views.admin_return_detail, name='admin_return_detail'),
    path('manage/returns/<int:return_id>/update-status/', views.admin_update_return_status, name='admin_update_return_status'),
    path('manage/dashboard/', views.admin_dashboard_orders, name='admin_dashboard_orders'),
    
    path('manage/orders/<str:order_number>/update-tracking/', views.admin_update_tracking, name='admin_update_tracking'),
    path('manage/orders/<str:order_number>/export-csv/', views.export_order_csv, name='export_order_csv'),
    path('manage/orders/<str:order_number>/edit/', views.admin_order_edit, name='admin_order_edit'),
    path('manage/orders/<str:order_number>/modal/', views.admin_order_detail_modal, name='admin_order_detail_modal'),
    path('manage/orders/<str:order_number>/delete/', views.admin_order_delete, name='admin_order_delete'),

    
]
