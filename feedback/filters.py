import django_filters
from django.db.models import Q
from django_filters import rest_framework as filters

from .models import Feedback, FeedbackTag
from django.contrib.auth import get_user_model

User = get_user_model()


class FeedbackFilter(filters.FilterSet):
    # exact / boolean
    reviewed = filters.BooleanFilter(field_name="reviewed")
    feedback_type = filters.CharFilter(field_name="feedback_type", lookup_expr="iexact")
    user = filters.ModelChoiceFilter(queryset=User.objects.all())
    ip_address = filters.CharFilter(lookup_expr="icontains")
    source_url = filters.CharFilter(lookup_expr="icontains")

    # rating range
    rating_min = filters.NumberFilter(field_name="rating", lookup_expr="gte")
    rating_max = filters.NumberFilter(field_name="rating", lookup_expr="lte")

    # date ranges
    submitted_after = filters.DateTimeFilter(field_name="submitted_at", lookup_expr="gte")
    submitted_before = filters.DateTimeFilter(field_name="submitted_at", lookup_expr="lte")
    feedback_after = filters.DateTimeFilter(field_name="feedback_date", lookup_expr="gte")
    feedback_before = filters.DateTimeFilter(field_name="feedback_date", lookup_expr="lte")
    reviewed_after = filters.DateTimeFilter(field_name="reviewed_at", lookup_expr="gte")
    reviewed_before = filters.DateTimeFilter(field_name="reviewed_at", lookup_expr="lte")

    # tag filtering (many-to-many)
    tags = filters.ModelMultipleChoiceFilter(
        field_name="tags__id",
        to_field_name="id",
        queryset=FeedbackTag.objects.all(),
        conjoined=False
    )

    # full-text search on title/message
    search = filters.CharFilter(method="filter_search", label="Search title or message")

    class Meta:
        model = Feedback
        fields = [
            "reviewed",
            "feedback_type",
            "user",
            "ip_address",
            "source_url",
            "rating_min", "rating_max",
            "submitted_after", "submitted_before",
            "feedback_after", "feedback_before",
            "reviewed_after", "reviewed_before",
            "tags",
            "search",
        ]

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(title__icontains=value) |
            Q(message__icontains=value)
        )



