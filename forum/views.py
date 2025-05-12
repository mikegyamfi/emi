from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Category, Thread, ThreadReply, ThreadReplyVote, ThreadSubscription, ForumNotification
from .permissions import IsAuthorOrReadOnly, IsThreadNotLocked
from .serializers import (
    CategorySerializer, ThreadListSerializer, ThreadDetailSerializer,
    ThreadCreateSerializer, ThreadReplySerializer, ThreadReplyCreateSerializer,
    VoteSerializer, ForumNotificationSerializer
)


@extend_schema(tags=["Forum Categories"])
class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAdminUser]
    lookup_field = 'slug'

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return super().get_permissions()


@extend_schema(tags=["Forum Threads"])
class ThreadViewSet(viewsets.ModelViewSet):
    queryset = Thread.objects.all()
    lookup_field = 'slug'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category', 'author', 'is_pinned']
    search_fields = ['title', 'content']
    ordering_fields = ['created_at', 'updated_at', 'views']

    def get_queryset(self):
        category_slug = self.request.query_params.get('category_slug')
        if category_slug:
            return Thread.objects.filter(category__slug=category_slug)
        return Thread.objects.all()

    def get_serializer_class(self):
        if self.action == 'create':
            return ThreadCreateSerializer
        elif self.action == 'list':
            return ThreadListSerializer
        return ThreadDetailSerializer

    def get_permissions(self):
        if self.action in ['update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated(), IsAuthorOrReadOnly()]
        elif self.action in ['create']:
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.views += 1
        instance.save()
        return super().retrieve(request, *args, **kwargs)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def subscribe(self, request, slug=None):
        thread = self.get_object()
        subscription, created = ThreadSubscription.objects.get_or_create(
            user=request.user,
            thread=thread
        )

        if created:
            return Response({'status': 'subscribed'}, status=status.HTTP_201_CREATED)
        return Response({'status': 'already subscribed'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def unsubscribe(self, request, slug=None):
        thread = self.get_object()
        try:
            subscription = ThreadSubscription.objects.get(
                user=request.user,
                thread=thread
            )
            subscription.delete()
            return Response({'status': 'unsubscribed'}, status=status.HTTP_200_OK)
        except ThreadSubscription.DoesNotExist:
            return Response({'status': 'not subscribed'}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def pin(self, request, slug=None):
        thread = self.get_object()
        thread.is_pinned = True
        thread.save()
        return Response({'status': 'pinned'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def unpin(self, request, slug=None):
        thread = self.get_object()
        thread.is_pinned = False
        thread.save()
        return Response({'status': 'unpinned'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def lock(self, request, slug=None):
        thread = self.get_object()
        thread.is_locked = True
        thread.save()
        return Response({'status': 'locked'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def unlock(self, request, slug=None):
        thread = self.get_object()
        thread.is_locked = False
        thread.save()
        return Response({'status': 'unlocked'}, status=status.HTTP_200_OK)


@extend_schema(tags=["Forum Replies"])
class ReplyViewSet(viewsets.ModelViewSet):
    queryset = ThreadReply.objects.all()
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['thread', 'author', 'is_solution']

    def get_serializer_class(self):
        if self.action == 'create':
            return ThreadReplyCreateSerializer
        return ThreadReplySerializer

    def get_permissions(self):
        if self.action in ['create']:
            return [permissions.IsAuthenticated(), IsThreadNotLocked()]
        elif self.action in ['update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated(), IsAuthorOrReadOnly(), IsThreadNotLocked()]
        return [permissions.AllowAny()]

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def vote(self, request, pk=None):
        reply = self.get_object()
        vote_type = request.data.get('vote_type')

        if vote_type not in [1, -1]:
            return Response({'error': 'Invalid vote type'}, status=status.HTTP_400_BAD_REQUEST)

        vote, created = ThreadReplyVote.objects.update_or_create(
            user=request.user,
            reply=reply,
            defaults={'vote_type': vote_type}
        )

        serializer = VoteSerializer(vote)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def mark_solution(self, request, pk=None):
        reply = self.get_object()
        thread = reply.thread

        # Only thread author or admin can mark solution
        if request.user != thread.author and not request.user.is_staff:
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

        # Reset any existing solution
        thread.replies.filter(is_solution=True).update(is_solution=False)

        # Mark this reply as solution
        reply.is_solution = True
        reply.save()

        # Notify the reply author
        if reply.author != request.user:
            ForumNotification.objects.create(
                recipient=reply.author,
                thread=thread,
                reply=reply,
                notification_type='solution'
            )

        return Response({'status': 'marked as solution'}, status=status.HTTP_200_OK)


@extend_schema(tags=["Forum Notifications"])
class ForumNotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ForumNotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ForumNotification.objects.filter(recipient=self.request.user).order_by('-created_at')

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save()
        return Response({'status': 'marked as read'})

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        self.get_queryset().update(is_read=True)
        return Response({'status': 'all marked as read'})
