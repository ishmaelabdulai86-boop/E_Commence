from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    name = 'notifications'
    default_auto_field = 'django.db.models.BigAutoField'
    
    def ready(self):
        """Load signals when app is ready"""
        import notifications.signals  # noqa

