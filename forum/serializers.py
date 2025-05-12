from django.utils.text import slugify
from rest_framework import serializers

from account.serializers import UserMinimalSerializer
from .models import Category, Thread, ThreadReply, ThreadReplyVote, ThreadSubscription, ForumNotification
from django.contrib.auth import get_user_model


class CategorySerializer(serializers.ModelSerializer):
    thread_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'description', 'slug', 'thread_count', 'created_at']

    def get_thread_count(self, obj):
        return obj.threads.count()


class ThreadListSerializer(serializers.ModelSerializer):
    author = UserMinimalSerializer(read_only=True)
    category_name = serializers.ReadOnlyField(source='category.name')
    reply_count = serializers.ReadOnlyField()
    last_activity = serializers.SerializerMethodField()

    class Meta:
        model = Thread
        fields = ['id', 'title', 'slug', 'author', 'category', 'category_name',
                  'is_pinned', 'is_locked', 'views', 'reply_count',
                  'created_at', 'updated_at', 'last_activity']

    def get_last_activity(self, obj):
        latest_reply = obj.replies.order_by('-created_at').first()
        if latest_reply:
            return latest_reply.created_at
        return obj.created_at


class ThreadCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Thread
        fields = ['title', 'content', 'category']

    def validate_title(self, value):
        slug = slugify(value)
        if Thread.objects.filter(slug=slug).exists():
            raise serializers.ValidationError("Thread with this title already exists.")
        return value

    def create(self, validated_data):
        user = self.context['request'].user
        thread = Thread.objects.create(author=user, **validated_data)
        ThreadSubscription.objects.create(user=user, thread=thread)
        return thread


class VoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ThreadReplyVote
        fields = ['id', 'vote_type', 'created_at']
        read_only_fields = ['id', 'created_at']


class ThreadReplySerializer(serializers.ModelSerializer):
    author = UserMinimalSerializer(read_only=True)
    votes_count = serializers.SerializerMethodField()
    current_user_vote = serializers.SerializerMethodField()

    class Meta:
        model = ThreadReply
        fields = ['id', 'thread', 'author', 'content', 'is_solution',
                  'votes_count', 'current_user_vote', 'created_at', 'updated_at']
        read_only_fields = ['is_solution']

    def get_votes_count(self, obj):
        return sum(vote.vote_type for vote in obj.votes.all())

    def get_current_user_vote(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            try:
                vote = obj.votes.get(user=request.user)
                return vote.vote_type
            except ThreadReplyVote.DoesNotExist:
                pass
        return None


class ThreadReplyCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ThreadReply
        fields = ['thread', 'content']

    def create(self, validated_data):
        user = self.context['request'].user
        reply = ThreadReply.objects.create(author=user, **validated_data)

        # Create notifications for thread subscribers
        thread = validated_data['thread']
        subscribers = ThreadSubscription.objects.filter(thread=thread).exclude(user=user)

        for subscription in subscribers:
            ForumNotification.objects.create(
                recipient=subscription.user,
                thread=thread,
                reply=reply,
                notification_type='reply'
            )

        return reply


class ThreadDetailSerializer(serializers.ModelSerializer):
    author = UserMinimalSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    replies = ThreadReplySerializer(many=True, read_only=True)
    is_subscribed = serializers.SerializerMethodField()

    class Meta:
        model = Thread
        fields = ['id', 'title', 'slug', 'content', 'author', 'category',
                  'is_pinned', 'is_locked', 'views', 'created_at',
                  'updated_at', 'replies', 'is_subscribed']

    def get_is_subscribed(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return ThreadSubscription.objects.filter(user=request.user, thread=obj).exists()
        return False


class ThreadSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ThreadSubscription
        fields = ['id', 'thread', 'created_at']
        read_only_fields = ['id', 'created_at']


class ForumNotificationSerializer(serializers.ModelSerializer):
    thread_title = serializers.ReadOnlyField(source='thread.title')
    thread_slug = serializers.ReadOnlyField(source='thread.slug')

    class Meta:
        model = ForumNotification
        fields = ['id', 'thread', 'thread_title', 'thread_slug', 'reply',
                  'notification_type', 'is_read', 'created_at']
        read_only_fields = ['id', 'thread', 'reply', 'notification_type', 'created_at']






































