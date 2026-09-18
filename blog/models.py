from django.db import models
from django.utils.text import slugify
from ckeditor_uploader.fields import RichTextUploadingField
from affiliates.models import AffiliateProduct


class BlogCategory(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class BlogPost(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True)
    category = models.ForeignKey(BlogCategory, on_delete=models.SET_NULL, null=True, blank=True)
    excerpt = models.CharField(max_length=300)
    content = RichTextUploadingField(help_text="Rich text content")
    featured_image_url = models.URLField(blank=True)
    affiliate_products = models.ManyToManyField(AffiliateProduct, blank=True)
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(auto_now_add=True)

    # SEO FIELDS
    meta_title = models.CharField(
        max_length=70, blank=True,
        help_text="SEO title tag — 50-60 chars ideal. Blank = post title use hoga"
    )
    meta_description = models.CharField(
        max_length=160, blank=True,
        help_text="SEO meta description — 150-160 chars ideal. Blank = excerpt use hoga"
    )
    meta_keywords = models.CharField(
        max_length=250, blank=True,
        help_text="Comma-separated keywords, jaise: paris weather, europe travel, august trip"
    )

    def get_meta_title(self):
        return self.meta_title if self.meta_title else self.title

    def get_meta_description(self):
        return self.meta_description if self.meta_description else self.excerpt

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title
