from django.urls import path

from accounts.views import MagicLinkConsumeView, MagicLinkRequestView

urlpatterns = [
    path("auth/magic-link/request", MagicLinkRequestView.as_view(), name="magic-link-request"),
    path("auth/magic-link/consume", MagicLinkConsumeView.as_view(), name="magic-link-consume"),
]
