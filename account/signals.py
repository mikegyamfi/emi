from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver
from .models import (
    CustomUser, UserProfile, VendorProfile,
    AggregatorProfile, AgentProfile, Role,
)


# 1-A. generic profile (unchanged)
@receiver(post_save, sender=CustomUser)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)


# 1-B. role-specific profile mapping
ROLE_MAP = {
    "vendor": VendorProfile,
    "aggregator": AggregatorProfile,
    "agent": AgentProfile,
}


def _ensure_role_profiles(user):
    # role is now M2M → grab slugs
    roles = list(user.role.values_list("slug", flat=True))
    for slug in roles:
        model = ROLE_MAP.get(slug)
        if model:
            model.objects.get_or_create(user=user)


@receiver(post_save, sender=CustomUser)
def create_initial_role_profiles(sender, instance, created, **kwargs):
    if created:
        _ensure_role_profiles(instance)


@receiver(m2m_changed, sender=CustomUser.role.through)
def create_profiles_on_role_add(sender, instance, action, **kwargs):
    if action == "post_add":
        _ensure_role_profiles(instance)




