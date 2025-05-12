from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class FeedbackTag(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class Feedback(models.Model):
    content_type = models.ForeignKey(
        ContentType,
        limit_choices_to=models.Q(app_label='product_service_management', model__in=('product', 'service')),
        on_delete=models.CASCADE, null=True, blank=True
    )
    object_id = models.UUIDField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    FEEDBACK_TYPE_CHOICES = [
        ('issue', 'Issue'),
        ('suggestion', 'Suggestion'),
        ('rating', 'Rating'),
    ]
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="feedbacks")
    feedback_type = models.CharField(max_length=20, choices=FEEDBACK_TYPE_CHOICES)
    title = models.CharField(max_length=255)
    message = models.TextField(blank=True)
    rating = models.PositiveIntegerField(null=True, blank=True)  # for 'rating' type
    attachment = models.ImageField(upload_to='feedback_attachments/', null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed = models.BooleanField(default=False)
    feedback_date = models.DateTimeField(default=timezone.now)
    source_url = models.URLField(blank=True, null=True)
    reviewed_at = models.DateTimeField(blank=True, null=True)
    tags = models.ManyToManyField(FeedbackTag, blank=True)
    upvotes = models.ManyToManyField(User, related_name="feedback_upvotes", blank=True)
    user_agent = models.TextField(blank=True, null=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)

    def __str__(self):
        return f"{self.feedback_type} - {self.title}"

    def mark_reviewed(self):
        self.reviewed = True
        self.reviewed_at = timezone.now()
        self.save(update_fields=["reviewed", "reviewed_at"])


class FeedbackResponse(models.Model):
    re = models.ForeignKey('Feedback', on_delete=models.CASCADE, related_name="responses", null=True, blank=True)
    response_text = models.TextField(blank=True, null=True)
    response_title = models.CharField(max_length=255, null=True, blank=True)
    response_date = models.DateTimeField(default=timezone.now)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="responses")
    response_attachment = models.ImageField(upload_to='feedback_response_attachments/', null=True, blank=True)


    def __str__(self):
        return self.response_title












