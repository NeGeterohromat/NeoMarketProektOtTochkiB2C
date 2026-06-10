from django.urls import path
from .views import OrderCreateView, OrderCancelView

app_name = 'ord'

urlpatterns = [
    path('api/v1/orders/', OrderCreateView.as_view(), name='order-create'),
    path('api/v1/orders/<uuid:order_id>/cancel/', OrderCancelView.as_view(), name='order-cancel'),
]
