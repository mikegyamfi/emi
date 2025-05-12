# forum/admin.py   (or business.admin if you keep it inside the same app)
from django.contrib import admin
from django.utils.html import format_html
from django.utils.text import Truncator

from .models import (
    Category,
    Thread,
    ThreadReply,
    ThreadReplyVote,
    ThreadSubscription,
    ForumNotification,
)


# ────────────────────────────────────────────────────────────
#  Helpers
# ────────────────────────────────────────────────────────────
def short(text, length=60):
    return Truncator(text).chars(length, truncate=' …')


# ────────────────────────────────────────────────────────────
#  Category
# ────────────────────────────────────────────────────────────
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("name",)


# ────────────────────────────────────────────────────────────
#  Inline replies inside a Thread
# ────────────────────────────────────────────────────────────
class ThreadReplyInline(admin.TabularInline):
    model = ThreadReply
    extra = 0
    fields = ("author", "short_content", "is_solution", "is_visible", "created_at")
    readonly_fields = fields

    def short_content(self, obj):
        return short(obj.content, 50)
    short_content.short_description = "Content"


# ────────────────────────────────────────────────────────────
#  Thread
# ────────────────────────────────────────────────────────────
@admin.register(Thread)
class ThreadAdmin(admin.ModelAdmin):
    inlines = (ThreadReplyInline,)

    list_display = (
        "title", "category", "author",
        "reply_count", "views",
        "is_pinned", "is_locked",
        "created_at",
    )
    list_filter = ("category", "is_pinned", "is_locked", "author")
    search_fields = ("title", "content", "author__email", "author__username")
    prepopulated_fields = {"slug": ("title",)}
    list_editable = ("is_pinned", "is_locked")
    readonly_fields = ("views", "reply_count", "created_at", "updated_at", "slug")

    fieldsets = (
        (None, {"fields": ("category", "author", "title", "slug", "content")}),
        ("Meta", {"fields": ("is_pinned", "is_locked", "views", "reply_count")}),
        ("Dates", {"fields": ("created_at", "updated_at")}),
    )

    def reply_count(self, obj):
        return obj.replies.count()
    reply_count.short_description = "Replies"


# ────────────────────────────────────────────────────────────
#  Thread Reply
# ────────────────────────────────────────────────────────────
@admin.register(ThreadReply)
class ThreadReplyAdmin(admin.ModelAdmin):
    list_display = (
        "short_content", "thread", "author",
        "is_solution", "is_visible",
        "created_at",
    )
    list_filter = ("is_solution", "is_visible", "thread", "author")
    search_fields = ("content", "thread__title", "author__email")
    actions = ["mark_solution", "toggle_visibility"]

    def short_content(self, obj):
        return short(obj.content, 80)
    short_content.short_description = "Content"

    def mark_solution(self, request, queryset):
        updated = queryset.update(is_solution=True)
        self.message_user(request, f"{updated} reply(ies) marked as solution.")
    mark_solution.short_description = "Mark selected as solution"

    def toggle_visibility(self, request, queryset):
        updated = 0
        for reply in queryset:
            reply.is_visible = not reply.is_visible
            reply.save(update_fields=["is_visible"])
            updated += 1
        self.message_user(request, f"Toggled visibility for {updated} reply(ies).")
    toggle_visibility.short_description = "Toggle visibility"


# ────────────────────────────────────────────────────────────
#  Reply Vote
# ────────────────────────────────────────────────────────────
@admin.register(ThreadReplyVote)
class ThreadReplyVoteAdmin(admin.ModelAdmin):
    list_display = ("user", "reply", "vote_type", "created_at")
    list_filter = ("vote_type",)
    search_fields = ("user__email", "reply__content")


# ────────────────────────────────────────────────────────────
#  Subscription
# ────────────────────────────────────────────────────────────
@admin.register(ThreadSubscription)
class ThreadSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "thread", "created_at")
    search_fields = ("user__email", "thread__title")


# ────────────────────────────────────────────────────────────
#  Notification
# ────────────────────────────────────────────────────────────
@admin.register(ForumNotification)
class ForumNotificationAdmin(admin.ModelAdmin):
    list_display = (
        "recipient", "notification_type",
        "thread", "reply",
        "is_read", "created_at",
    )
    list_filter = ("is_read", "notification_type")
    search_fields = ("recipient__email", "thread__title", "reply__content")
