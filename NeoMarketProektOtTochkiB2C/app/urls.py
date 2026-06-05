from django.urls import path
from .views import CatalogProductsView, CatalogFacetsView, ProductDetailView

app_name = 'app'

urlpatterns = [
    path('products', CatalogProductsView.as_view(), name='products-list'),
    # ⚠️ Предлагаемый эндпоинт для фасетов (отсутствует в b2c.yaml)
    path('facets', CatalogFacetsView.as_view(), name='facets'),
    path('products/<uuid:id>', ProductDetailView.as_view(), name='product_detail')
]
