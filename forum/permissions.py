# permissions
# forums/permissions.py
from rest_framework import permissions


class IsAuthorOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow authors of an object to edit it.
    """

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions are only allowed to the author or staff
        return obj.author == request.user or request.user.is_staff


class IsThreadNotLocked(permissions.BasePermission):
    """
    Custom permission to prevent actions on locked threads.
    """

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request
        if request.method in permissions.SAFE_METHODS:
            return True

        # For replies, check if the thread is locked
        if hasattr(obj, 'thread'):
            return not obj.thread.is_locked

        # For threads, direct check
        return not obj.is_locked






