#!/usr/bin/env python3
import os
import django

# 1) Point to your settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'emi_skeleton.settings')
# 2) Bootstrap Django
django.setup()

from django.db import transaction
from django.db.models import Count
from account.models import UserProfile, VendorProfile


def clean_model_duplicates(Model, name):
    """
    For the given Model (with a OneToOneField to User via 'user'),
    delete all but the earliest (lowest-id) instance per user.
    """
    print(f"Checking {name} for duplicates...")
    # Find all user_ids with more than one entry
    dup_users = (
        Model.objects
             .values('user')
             .annotate(cnt=Count('id'))
             .filter(cnt__gt=1)
    )

    if not dup_users:
        print(f"  No duplicates found in {name}.\n")
        return

    with transaction.atomic():
        for entry in dup_users:
            uid = entry['user']
            # Fetch all entries for this user, ordered by id
            objs = list(Model.objects.filter(user_id=uid).order_by('id'))
            # Keep the first, delete the rest
            to_delete = objs[1:]
            for obj in to_delete:
                print(f"  Deleting {name}(id={obj.id}) for user_id={uid}")
                obj.delete()
    print(f"Done cleaning {name}.\n")


def main():
    clean_model_duplicates(UserProfile,   'UserProfile')
    clean_model_duplicates(VendorProfile, 'VendorProfile')
    print("All duplicate profiles removed.")


if __name__ == '__main__':
    main()
