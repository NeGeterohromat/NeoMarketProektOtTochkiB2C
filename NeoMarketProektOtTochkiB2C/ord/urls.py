from django.urls import path
from .views import OrderCreateView

app_name = 'ord'

urlpatterns = [
    path('api/v1/orders/', OrderCreateView.as_view(), name='order-create'),
]
