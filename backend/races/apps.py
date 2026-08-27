from django.apps import AppConfig


class RacesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "races"

    def ready(self):
        from races import signals  # noqa: F401
