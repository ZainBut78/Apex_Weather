from django.http import HttpResponseRedirect, Http404
from django.views.decorators.http import require_GET
from .models import AffiliateProduct, AffiliateClick


@require_GET
def affiliate_click_redirect(request, product_id):
    try:
        product = AffiliateProduct.objects.get(id=product_id, is_active=True)
    except AffiliateProduct.DoesNotExist:
        raise Http404("Product not found")

    # source_feature column CharField(max_length=50) hai. Lamba query
    # param seedha DB mein jane se Postgres "value too long" error deta
    # tha aur redirect 500 ban jata tha.
    source = (request.GET.get("source") or "unknown").strip()[:50] or "unknown"
    AffiliateClick.objects.create(product=product, source_feature=source)

    return HttpResponseRedirect(product.affiliate_url)
