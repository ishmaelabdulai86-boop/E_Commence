# apps/users/models.py
from django.contrib.auth.models import AbstractUser
from django.db import models

# users/models.py - Add these fields to your User model
class User(AbstractUser):
    ROLE_CHOICES = (
        ('customer', 'Customer'),
        ('seller', 'Seller'),
        ('admin', 'Administrator'),
    )
    
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='customer')
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    zip_code = models.CharField(max_length=20, blank=True)
    profile_picture = models.ImageField(upload_to='profiles/', blank=True)
    email_verified = models.BooleanField(default=False)
    phone_verified = models.BooleanField(default=False)
    
    # Add these two fields for email verification
    email_verification_token = models.CharField(max_length=100, blank=True, null=True)
    email_token_created = models.DateTimeField(null=True, blank=True)
    
    otp = models.CharField(max_length=6, blank=True)
    otp_expiry = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'users'
    
    def __str__(self):
        return self.username

    @property
    def profile_picture_url(self):
        """Safe property to get profile picture URL, returns None if not set."""
        if self.profile_picture and hasattr(self.profile_picture, 'url'):
            return self.profile_picture.url
        return None
    