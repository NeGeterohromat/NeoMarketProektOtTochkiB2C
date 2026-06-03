import uuid
from unittest.mock import patch
from django.test import override_settings
from django.urls import reverse
from app.services import B2BClient
from rest_framework.test import APITestCase, APIClient
from django.contrib.auth import get_user_model
from .models import CartItem
from app.services import B2BClient

User = get_user_model()

@override_settings(B2B_BASE_URL='http://mock-b2b.local')
class CartAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='password')
        self.sku_id = uuid.uuid4()
        self.session_id = str(uuid.uuid4())
        self.product_id = uuid.uuid4()
        
        # Мокаем B2B-ответ по умолчанию (доступный товар)
        self.mock_b2b_response = {
            'items': [{
                'id': str(self.sku_id),
                'product_id': str(self.product_id),
                'name': 'Test Product',
                'price': 1000,
                'active_quantity': 10,
                'status': 'MODERATED'
            }]
        }

    def _mock_b2b_skus(self, sku_id=None, available=True, qty=10):
        """Хелпер для динамического мокинга B2B"""
        def side_effect(url, **kwargs):
            if 'batch' in url:
                data = kwargs.get('data', {})
                items = []
                for sid in data.get('sku_ids', []):
                    items.append({
                        'id': sid,
                        'product_id': str(uuid.uuid4()),
                        'name': 'Test Product',
                        'price': 1000,
                        'active_quantity': qty if available else 0,
                        'status': 'MODERATED' if available else 'BLOCKED'
                    })
                return {'items': items}
            return {}
        return side_effect

    def test_add_sku_increments_quantity_if_already_in_cart(self):
        with patch.object(B2BClient,'_call_b2b') as mock_post:
            mock_post.side_effect = self._mock_b2b_skus()
            self.client.credentials(HTTP_X_SESSION_ID=self.session_id)
            url = reverse('cart:cart-items')
            # Первое добавление
            resp1 = self.client.post(url, {'sku_id': str(self.sku_id), 'quantity': 2})
            self.assertEqual(resp1.status_code, 201)
        
                # Повторное добавление
            resp2 = self.client.post(url, {'sku_id': str(self.sku_id), 'quantity': 3})
            self.assertEqual(resp2.status_code, 200)
        
            cart = resp2.json()
            item = next(i for i in cart['items'] if i['sku_id'] == str(self.sku_id))
            self.assertEqual(item['quantity'], 5) # 2 + 3

    def test_get_cart_enriched_with_b2b_data(self):
        with patch.object(B2BClient,'_call_b2b') as mock_post:
            mock_post.side_effect = self._mock_b2b_skus()
            self.client.credentials(HTTP_X_SESSION_ID=self.session_id)
        
            CartItem.objects.create(session_id=self.session_id, sku_id=self.sku_id, quantity=2)
        
            url = reverse('cart:cart-detail')
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200)
        
            data = resp.json()
            self.assertEqual(data['items_count'], 2)
            self.assertEqual(data['subtotal'], 2000) # 2 * 1000
            self.assertTrue(data['is_valid'])
            item = data['items'][0]
            self.assertEqual(item['unit_price'], 1000)
            self.assertTrue(item['is_available'])

    
    def test_unavailable_sku_shown_with_reason(self):
        with patch.object(B2BClient,'_call_b2b') as mock_post:
            mock_post.side_effect = self._mock_b2b_skus(available=False, qty=0)
            self.client.credentials(HTTP_X_SESSION_ID=self.session_id)
        
            CartItem.objects.create(session_id=self.session_id, sku_id=self.sku_id, quantity=1)
        
            url = reverse('cart:cart-detail')
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200)
        
            data = resp.json()
            item = data['items'][0]
            self.assertFalse(item['is_available'])
            self.assertEqual(item['unavailable_reason'], 'OUT_OF_STOCK')
            self.assertEqual(item['line_total'], 0) # Не входит в total_amount
            self.assertEqual(data['subtotal'], 0)
            self.assertFalse(data['is_valid'])

    def test_guest_cart_merged_on_login(self):
        with patch.object(B2BClient,'_call_b2b') as mock_post:
            mock_post.side_effect = self._mock_b2b_skus()
        
            # 1. Гость добавляет 3 шт.
            self.client.credentials(HTTP_X_SESSION_ID=self.session_id)
            url = reverse('cart:cart-items')
            self.client.post(url, {'sku_id': str(self.sku_id), 'quantity': 3})
        
            # 2. Пользователь уже имеет 5 шт. этого SKU
            CartItem.objects.create(user=self.user, sku_id=self.sku_id, quantity=5)
        
            # 3. Авторизуемся и мержим
            self.client.force_authenticate(user=self.user)
            self.client.credentials(HTTP_X_SESSION_ID=self.session_id) # Передаем для мержа
        
            merge_url = reverse('cart:cart-merge')
            resp = self.client.post(merge_url)
            self.assertEqual(resp.status_code, 200)
        
            # Проверка: quantity = MAX(3, 5) = 5
            cart = resp.json()
            item = next(i for i in cart['items'] if i['sku_id'] == str(self.sku_id))
            self.assertEqual(item['quantity'], 5)
        
            # Проверка БД: гостевая запись удалена или перенесена
            self.assertEqual(CartItem.objects.filter(session_id=self.session_id).count(), 0)
            self.assertEqual(CartItem.objects.filter(user=self.user).count(), 1)