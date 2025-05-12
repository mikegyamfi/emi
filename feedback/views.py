import csv
from uuid import UUID

from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.http import HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response

from core.response import ok, fail
from .filters import FeedbackFilter
from .models import Feedback, FeedbackTag
from .serializers import FeedbackSerializer, FeedbackTagSerializer


@extend_schema(tags=["Feedbacks"])
class FeedbackViewSet(viewsets.ModelViewSet):
    """
    POST   /feedback/                → leave feedback (auth only)
    GET    /feedback/                → list ALL feedback (admin only)
    GET    /feedback/{pk}/           → retrieve one (admin only)
    GET    /feedback/mine/           → list your feedback (auth only)
    POST   /feedback/{pk}/upvote/    → upvote (auth only)
    GET    /feedback/export_csv/     → CSV export (admin only)
    GET    /feedback/export_json/    → JSON export (admin only)
    GET    /feedback/insights/       → stats (admin only)
    """
    queryset = Feedback.objects.all().order_by('-submitted_at')
    serializer_class = FeedbackSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = FeedbackFilter

    def get_permissions(self):
        # admin‐only reads & exports
        if self.action in ('list', 'retrieve',
                           'export_csv', 'export_json', 'insights'):
            return [permissions.IsAdminUser()]
        # your own feedback & upvote & create → auth
        if self.action in ('mine', 'upvote', 'create'):
            return [permissions.IsAuthenticated()]
        # tag txt etc. left untouched
        return [permissions.AllowAny()]

    def list(self, request, *args, **kwargs):
        """Admin: list all feedback."""
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        ser = self.get_serializer(page or self.get_queryset(), many=True)
        return (
            self.get_paginated_response(ser.data)
            if page else ok("OK", ser.data)
        )

    def retrieve(self, request, *args, **kwargs):
        """Admin: retrieve one."""
        obj = self.get_object()
        return ok("OK", self.get_serializer(obj).data)

    @action(detail=False, methods=['get'], url_path='mine')
    def mine(self, request):
        """GET /feedback/mine/ – your own feedback."""
        qs = self.filter_queryset(self.get_queryset().filter(user=request.user))
        page = self.paginate_queryset(qs)
        ser = self.get_serializer(page or qs, many=True)
        return (
            self.get_paginated_response(ser.data)
            if page else ok("OK", ser.data)
        )

    def create(self, request, *args, **kwargs):
        """POST /feedback/ – submit new feedback (auth only)."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # capture IP & UA
        ip = request.META.get('REMOTE_ADDR')
        ua = request.META.get('HTTP_USER_AGENT')
        referer = request.META.get('HTTP_REFERER') or request.build_absolute_uri()
        try:
            serializer.save(user=request.user, ip_address=ip, user_agent=ua, source_url=referer, )
        except Exception as e:
            return fail(str(e), status=status.HTTP_400_BAD_REQUEST)

        return ok("Feedback submitted", serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def upvote(self, request, pk=None):
        """POST /feedback/{pk}/upvote/ – upvote a feedback."""
        fb = self.get_object()
        if request.user in fb.upvotes.all():
            return fail("Already upvoted", status=status.HTTP_400_BAD_REQUEST)
        fb.upvotes.add(request.user)
        return ok("Upvoted")

    @action(detail=False, methods=['get'], url_path='export_csv')
    def export_csv(self, request):
        """Admin: CSV export."""
        qs = self.filter_queryset(self.get_queryset())
        resp = HttpResponse(content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="feedback.csv"'
        w = csv.writer(resp)
        w.writerow([
            'ID', 'Type', 'Title', 'Message', 'Rating',
            'User', 'Submitted', 'Reviewed', 'Reviewed At'
        ])
        for fb in qs:
            w.writerow([
                fb.id,
                fb.feedback_type,
                fb.title,
                fb.message or '',
                fb.rating or '',
                fb.user.email if fb.user else 'Anonymous',
                fb.submitted_at.strftime("%Y-%m-%d %H:%M"),
                'Yes' if fb.reviewed else 'No',
                fb.reviewed_at.strftime("%Y-%m-%d %H:%M") if fb.reviewed_at else ''
            ])
        return resp

    @action(detail=False, methods=['get'], url_path='export_json')
    def export_json(self, request):
        """Admin: JSON export."""
        qs = self.filter_queryset(self.get_queryset()).values()
        return ok("OK", list(qs))

    @action(detail=False, methods=['get'], url_path='insights')
    def insights(self, request):
        """Admin: feedback stats & rating distribution."""
        qs = self.filter_queryset(self.get_queryset())
        total = qs.count()
        by_type = list(qs.values('feedback_type').annotate(count=models.Count('id')))
        reviewed = qs.filter(reviewed=True).count()
        ratings = qs.filter(feedback_type='rating', rating__isnull=False)
        avg = ratings.aggregate(avg=models.Avg('rating'))['avg']
        dist = {
            str(r['rating']): r['count']
            for r in ratings.values('rating')
            .annotate(count=models.Count('id'))
        }
        for i in range(1, 6):
            dist.setdefault(str(i), 0)

        return ok("Insights", {
            'total': total,
            'by_type': by_type,
            'reviewed': reviewed,
            'unreviewed': total - reviewed,
            'average_rating': avg,
            'distribution': dist,
        })


@extend_schema(tags=["Feedbacks"])
class FeedbackTagViewSet(viewsets.ModelViewSet):
    queryset = FeedbackTag.objects.all()
    serializer_class = FeedbackTagSerializer
    permission_classes = [IsAdminUser]
