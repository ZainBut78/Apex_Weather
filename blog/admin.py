from django.contrib import admin

from .models import BlogCategory, BlogPost


@admin.register(BlogCategory)
class BlogCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "is_published", "published_at")
    # Iske baghair changelist har row ke liye category alag se fetch
    # karti thi (100 posts/page = 100 extra queries).
    list_select_related = ("category",)
    list_filter = ("is_published", "category")
    search_fields = ("title", "content", "meta_keywords")
    filter_horizontal = ("affiliate_products",)
    prepopulated_fields = {"slug": ("title",)}

    fieldsets = (
        ("Content", {
            "fields": ("title", "slug", "category", "excerpt",
                       "content", "featured_image_url", "affiliate_products")
        }),
        ("SEO Settings (On-Page SEO)", {
            "fields": ("meta_title", "meta_description", "meta_keywords"),
            "description": ("Yeh fields Google search results mein kaise "
                            "dikhega, control karte hain — blank chhod sakte "
                            "ho, defaults use ho jayenge."),
        }),
        ("Publishing", {
            "fields": ("is_published",)
        }),
    )
