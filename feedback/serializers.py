from uuid import UUID

from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers

from account.serializers import UserMinimalSerializer
from .models import Feedback, FeedbackTag


class FeedbackTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeedbackTag
        fields = ['id', 'name']


class FeedbackSerializer(serializers.ModelSerializer):
    model = serializers.ChoiceField(
        choices=[
            ('vendorproduct', 'VendorProduct'),
            ('vendorservice', 'VendorService')
        ],
        write_only=True,
        required=False,
    )
    object_id = serializers.UUIDField(write_only=True, required=False)

    tags = serializers.PrimaryKeyRelatedField(
        many=True, queryset=FeedbackTag.objects.all(), required=False
    )
    user = serializers.StringRelatedField(read_only=True)
    submitted_at = serializers.DateTimeField(read_only=True)
    source_url = serializers.URLField(read_only=True)

    class Meta:
        model = Feedback
        fields = (
            'id', 'model', 'object_id', 'user', 'feedback_type', 'title', 'message',
            'rating', 'attachment', 'submitted_at', 'source_url', 'tags',
        )
        read_only_fields = ('id', 'user', 'submitted_at')

    def create(self, validated_data):
        model = validated_data.pop('model', None)
        object_id = validated_data.pop('object_id', None)

        # if both provided, attach via ContentType
        if model and object_id:
            print(model, object_id)
            try:
                ct = ContentType.objects.get(
                    app_label='product_service_management', model=model
                )
                # validate uuid
                UUID(str(object_id))
                validated_data['content_type'] = ct
                validated_data['object_id'] = object_id
            except Exception:
                raise serializers.ValidationError("Invalid model/object_id combo.")

        # tie to current user (or leave null if anonymous)
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['user'] = request.user

        return super().create(validated_data)


# 1) a lean read‐only serializer for any feedback item
class FeedbackPublicSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    tags = FeedbackTagSerializer(many=True, read_only=True)
    upvotes_count = serializers.SerializerMethodField()
    attachment_url = serializers.SerializerMethodField()

    class Meta:
        model = Feedback
        fields = (
            'id',
            'user',
            'feedback_type',
            'title',
            'message',
            'rating',
            'attachment_url',
            'submitted_at',
            'tags',
            'upvotes_count',
        )

    def get_user(self, obj):
        return obj.user.get_full_name() if obj.user else "Anonymous"

    def get_upvotes_count(self, obj):
        return obj.upvotes.count()

    def get_attachment_url(self, obj):
        req = self.context.get("request")
        if obj.attachment:
            url = obj.attachment.url
            return req.build_absolute_uri(url) if req else url
        return None




