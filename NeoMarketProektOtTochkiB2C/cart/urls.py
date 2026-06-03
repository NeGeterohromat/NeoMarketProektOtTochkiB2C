from django.urls import path
from . import views

app_name = 'cart'

urlpatterns = [
    path('api/v1/cart', views.CartAPIView.as_view(), name='cart-detail'),
    path('api/v1/cart/items', views.CartItemAPIView.as_view(), name='cart-items'),
    path('api/v1/cart/items/<uuid:sku_id>', views.CartItemAPIView.as_view(), name='cart-item-detail'),
    path('api/v1/cart/validate', views.CartValidateAPIView.as_view(), name='cart-validate'),
    path('api/v1/cart/merge', views.CartMergeAPIView.as_view(), name='cart-merge'),
]
