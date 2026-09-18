from django.core.paginator import Paginator
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .models import BlogPost


@require_GET
def blog_list_view(request):
    page_number = request.GET.get("page", 1)
    per_page = 9

    # select_related ke baghair har post ka `p.category.name` ek alag
    # query karta tha (9 posts/page = 9 extra queries).
    posts = (BlogPost.objects
             .select_related("category")
             .filter(is_published=True)
             .order_by("-published_at"))
    paginator = Paginator(posts, per_page)
    page_obj = paginator.get_page(page_number)

    data = [{
        "title": p.title,
        "slug": p.slug,
        "excerpt": p.excerpt,
        "category": p.category.name if p.category else None,
        "featured_image": p.featured_image_url,
        "published_at": p.published_at,
    } for p in page_obj]

    return JsonResponse({
        "posts": data,
        "current_page": page_obj.number,
        "total_pages": paginator.num_pages,
        "total_posts": paginator.count,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
    })


@require_GET
def blog_detail_view(request, slug):
    try:
        post = (BlogPost.objects
                .select_related("category")
                .prefetch_related("affiliate_products")
                .get(slug=slug, is_published=True))
    except BlogPost.DoesNotExist:
        return JsonResponse({"error": "Post not found"}, status=404)

    products = [{
        "name": p.name,
        "affiliate_url": p.affiliate_url,
        "image_url": p.image_url,
        "price_display": p.price_display,
    } for p in post.affiliate_products.all()]

    return JsonResponse({
        "title": post.title,
        "slug": post.slug,
        "category": post.category.name if post.category else None,
        "content": post.content,
        "excerpt": post.excerpt,
        "featured_image": post.featured_image_url,
        "affiliate_products": products,
        "published_at": post.published_at,
        "meta_title": post.get_meta_title(),
        "meta_description": post.get_meta_description(),
        "meta_keywords": post.meta_keywords,
    })
