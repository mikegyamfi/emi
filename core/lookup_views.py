from rest_framework import viewsets, filters
from rest_framework.permissions import AllowAny


class Everyone(AllowAny):
    """Shortcut so we stay consistent with your other viewsets."""
    ...


class AutocompleteMixin(viewsets.ReadOnlyModelViewSet):
    """
    • disables pagination
    • honours ?search=<term>   (DRF SearchFilter → icontains)
    • optional ?limit=<n>      (# rows to return, default 20)
    """
    permission_classes = (Everyone,)
    pagination_class = None
    filter_backends = (filters.SearchFilter,)
    search_fields: tuple[str, ...] = ()        # each child sets this

    def get_queryset(self):
        limit = int(self.request.query_params.get("limit", 20))
        return self.base_qs.order_by("name")





