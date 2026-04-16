"""
URL configuration for E_Commence project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
# backend/ecommerce/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView
from analytics.views import admin_dashboard
from products.views import home_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home_view, name='home'),
    path('products/', include('products.urls')),
    path('cart/', include('cart.urls')),
    path('orders/', include('orders.urls')),
    # Redirect /checkout/ to /orders/checkout/
    path('checkout/', RedirectView.as_view(url='/orders/checkout/', permanent=False)),
    path('payments/', include('payments.urls')),
    path('users/', include('users.urls')),
    path('analytics/', include('analytics.urls')),
    
    path('admin/dashboard/', admin_dashboard, name='admin_dashboard'),

    # Notifications app
    path('notifications/', include('notifications.urls', namespace='notifications')),
    
    #path('login/', auth_views.LoginView.as_view(template_name='users/login.html'), name='login'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)