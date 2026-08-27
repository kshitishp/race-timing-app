from django.urls import path

from races.views import (
    BillingUsageListView,
    BulkSyncView,
    CheckpointListCreateView,
    ParticipantListCreateView,
    RaceDetailView,
    RaceListCreateView,
    RaceVolunteerListCreateView,
    ResultsExportView,
    ResultsView,
    TimingDetailView,
    TimingListView,
    TimingManualCreateView,
)

urlpatterns = [
    path("races", RaceListCreateView.as_view(), name="race-list"),
    path("races/<int:pk>", RaceDetailView.as_view(), name="race-detail"),
    path("races/<int:race_id>/checkpoints", CheckpointListCreateView.as_view(), name="checkpoint-list"),
    path("races/<int:race_id>/participants", ParticipantListCreateView.as_view(), name="participant-list"),
    path("races/<int:race_id>/volunteers", RaceVolunteerListCreateView.as_view(), name="volunteer-list"),
    path("races/<int:race_id>/timings", TimingListView.as_view(), name="timing-list"),
    path("races/<int:race_id>/timings/manual", TimingManualCreateView.as_view(), name="timing-manual-create"),
    path("races/<int:race_id>/results", ResultsView.as_view(), name="results"),
    path("races/<int:race_id>/results/export", ResultsExportView.as_view(), name="results-export"),
    path("races/<int:race_id>/billing", BillingUsageListView.as_view(), name="billing-usage"),
    path("timings/bulk-sync", BulkSyncView.as_view(), name="timing-bulk-sync"),
    path("timings/<int:pk>", TimingDetailView.as_view(), name="timing-detail"),
]
