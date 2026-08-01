from django.http import HttpResponseRedirect, Http404
from django.views.decorators.http import require_GET
from .models import AffiliateProduct, AffiliateClick


@require_GET
def affiliate_click_redirect(request, product_id):
    try:
        product = AffiliateProduct.objects.get(id=product_id, is_active=True)
    except AffiliateProduct.DoesNotExist:
        raise Http404("Product not found")

    source = request.GET.get("source", "unknown")
    AffiliateClick.objects.create(product=product, source_feature=source)

    return HttpResponseRedirect(product.affiliate_url)
