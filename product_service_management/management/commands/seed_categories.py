# your_app/management/commands/seed_categories.py
from django.core.management.base import BaseCommand
from product_service_management.models import Category

# your mapping of “root → [children]”
CATEGORY_MAP = {
    "Fashion Accessories": ["Women", "Men", "Boys", "Girls"],
    "Food & Groceries": ["Snacks & Delicacies", "Bakery", "Farm products"],
    "Health & Beauty": ["Hair care Product", "Herbal Products", "Skincare products"],
    "African Fabrics": ["Kente", "GTP", "Woodin", "Polished Cotton", "Tie & Dye"],
    "Arts, Crafts & Sewing": [
        "Painting", "Drawing", "Arts", "Sculpture", "Wood carving", "Gift Wrapping"
    ],
    "Detergents & Soaps": ["Afterwash", "Powered soap", "Liquid soap", "Antiseptic"],
    "Home tool & Appliances": ["Power tools", "Electrical appliances"],
    "Furniture": ["Living", "Kitchen", "Dining", "Bedroom", "Bathroom", "Toilet", "Office"],
    "Kitchen & Dining": ["Kitchen Utensils", "Cutlery & Knife Accessories", "Cooking appliances"],
    "Supplements": [],
    "Toiletries": ["Toilet paper", "Wipes"],
    "Baby products": ["Boys & Girls Products", "Skin Care", "Feeding", "Diapers"],
    "Cleaning": [],
    "Weeding": [],
    "Cooking": [],
    "Teaching": [],
    "Plumbing": [],
    "Carpenter": [],
    "Caregiving": [],
    "Housekeeping": [],
    "Masonry": [],
    "Tiling": [],
    "Driving": [],
    "Farming": [],
    "CV Writing": []
}


class Command(BaseCommand):
    help = "Seed the product_service_management.Category table with your master list."

    def handle(self, *args, **options):
        for root_name, children in CATEGORY_MAP.items():
            root, created = Category.objects.update_or_create(
                name=root_name,
                parent=None,
                defaults={"description": root_name, "is_active": True, "featured": False},
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created root category: {root_name}"))
            else:
                self.stdout.write(f"Root category already exists: {root_name}")

            for child_name in children:
                child, child_created = Category.objects.update_or_create(
                    name=child_name,
                    parent=root,
                    defaults={"description": child_name, "is_active": True, "featured": False},
                )
                if child_created:
                    self.stdout.write(self.style.SUCCESS(f"  └─ Created subcategory: {child_name}"))
                else:
                    self.stdout.write(f"  └─ Subcategory already exists: {child_name}")

        self.stdout.write(self.style.SUCCESS("✅  All categories & subcategories are seeded."))
