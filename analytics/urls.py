from django.urls import path
from . import views

app_name = 'analytics'

urlpatterns = [
    path('dashboard/', views.analytics_dashboard, name='analytics_dashboard'),
    path('sales-report/', views.sales_report, name='sales_report'),
    path('customers/', views.customer_analytics, name='customer_analytics'),
    path('products/', views.product_analytics, name='product_analytics'),
    path('api/sales-data/', views.api_sales_data, name='api_sales_data'),
    path('export/<str:report_type>/', views.export_report, name='export_report'),
    
    path('dashboard/', views.analytics_dashboard, name='analytics_dashboard'),
]