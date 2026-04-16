from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html

User = get_user_model()


class UserAdmin(BaseUserAdmin):
	model = User
	list_display = (
		'username', 'email', 'first_name', 'last_name', 'role', 'is_staff', 'is_active'
	)
	list_filter = ('role', 'is_staff', 'is_active')
	search_fields = ('username', 'email', 'first_name', 'last_name')
	ordering = ('username',)
	readonly_fields = ('profile_picture_display',)

	fieldsets = (
		(None, {'fields': ('username', 'password')}),
		(_('Personal info'), {'fields': ('first_name', 'last_name', 'email', 'phone', 'profile_picture_display')}),
		(_('Permissions'), {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
		(_('Important dates'), {'fields': ('last_login', 'date_joined')}),
		(_('Additional info'), {'fields': ('role', 'address', 'city', 'state', 'country', 'zip_code', 'email_verified', 'phone_verified')}),
	)

	def profile_picture_display(self, obj):
		"""Display profile picture or placeholder."""
		if obj.profile_picture:
			return format_html(
				'<img src="{}" width="100" height="100" style="border-radius: 5px;" />',
				obj.profile_picture.url
			)
		return '<em>No image</em>'
	profile_picture_display.short_description = 'Profile Picture Preview'

	add_fieldsets = (
		(None, {
			'classes': ('wide',),
			'fields': ('username', 'email', 'password1', 'password2', 'profile_picture'),
		}),
	)


admin.site.register(User, UserAdmin)
