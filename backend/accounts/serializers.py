from rest_framework import serializers

from accounts.models import MagicLink, User


class MagicLinkRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    purpose = serializers.ChoiceField(choices=MagicLink.Purpose.choices)
    race_id = serializers.IntegerField(required=False, allow_null=True)


class MagicLinkConsumeSerializer(serializers.Serializer):
    token = serializers.CharField()


class UserSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "name", "phone"]
