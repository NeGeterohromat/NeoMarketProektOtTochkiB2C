"""
This file demonstrates writing tests using the unittest module. These will pass
when you run "manage.py test".
"""

import requests
from requests.models import Response
from unittest.mock import patch, MagicMock, Mock
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status

from app.services import B2BClient


@override_settings(
    B2B_BASE_URL='http://127.0.0.1:8000',
    B2B_SERVICE_KEY='test-service-key'
)
class CatalogAPITests(APITestCase):
    """Тесты эндпоинтов каталога: /api/v1/catalog/*"""

    def setUp(self):
        """Базовая настройка перед каждым тестом"""
        self.service_key = 'test-service-key'
        self.client.defaults['HTTP_X_SERVICE_KEY'] = self.service_key
        self.category_id = '123e4567-e89b-12d3-a456-426614174001'
        self.product_id = '770e8400-e29b-41d4-a716-446655440002'

        # Моковый ответ от B2B для списка данных о товарах
        self.mock_b2b_products_data_response = [
  {
    "id": self.product_id,
    "seller_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "category_id": self.category_id,
    "title": "Iphone 15 Black 256GB",
    "slug": "IPHONE15BLACK256GB",
    "description": "string",
    "status": "CREATED",
    "images": [
      {
        "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "url": "https://cdn.neomarket.ru/images/iphone15.jpg",
        "ordering": 0
      }
    ],
    "characteristics": [
      {
        "name": "Бренд",
        "value": "Apple",
        "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
      }
    ],
    "skus": [
      {
        "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "product_id": self.product_id,
        "name": "string",
        "price": 0,
        "discount": 0,
        "stock_quantity": 12,
        "active_quantity": 0,
        "article": "string",
        "images": [
          {
            "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
            "url": "string",
            "ordering": 0
          }
        ],
        "characteristics": [
          {
            "name": "Бренд",
            "value": "Apple",
            "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
          }
        ]
      }
    ],
    "created_at": "2026-05-29T11:14:45.405Z",
    "updated_at": "2026-05-29T11:14:45.405Z"
  },
  {
    "id": '770e8400-e29b-41d4-a716-446655440003',
    "seller_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "category_id": self.category_id,
    "title": "Iphone 15 Black 256GB",
    "slug": "IPHONE15BLACK256GB",
    "description": "string",
    "status": "CREATED",
    "images": [
      {
        "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "url": "https://cdn.neomarket.ru/images/iphone15.jpg",
        "ordering": 0
      }
    ],
    "characteristics": [
      {
        "name": "Бренд",
        "value": "Apple",
        "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
      }
    ],
    "skus": [
      {
        "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "product_id": self.product_id,
        "name": "string",
        "price": 0,
        "discount": 0,
        "stock_quantity": 0,
        "active_quantity": 0,
        "article": "string",
        "images": [
          {
            "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
            "url": "string",
            "ordering": 0
          }
        ],
        "characteristics": [
          {
            "name": "Бренд",
            "value": "Apple",
            "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
          }
        ]
      }
    ],
    "created_at": "2026-05-29T11:14:45.405Z",
    "updated_at": "2026-05-29T11:14:45.405Z"
  }

]
        
        # Моковый ответ от B2B для списка товаров
        self.mock_b2b_products_response = {
  "items": [
    {
      "id": self.product_id,
      "title": "Iphone 15 Black 256GB",
      "slug": "IPHONE15BLACK256GB",
      "status": "CREATED",
      "category_id": self.category_id,
      "min_price": 65000,
      "cover_image": "https://cdn.neomarket.ru/images/iphone15.jpg",
      "created_at": "2026-05-29T10:19:20.615Z"
    },
    {
      "id": '770e8400-e29b-41d4-a716-446655440003', #other id
      "title": "Iphone 16 Black 256GB",
      "slug": "IPHONE16BLACK256GB",
      "status": "CREATED",
      "category_id": '123e4567-e89b-12d3-a456-426614174002', #other id
      "min_price": 67000,
      "cover_image": "https://cdn.neomarket.ru/images/iphone16.jpg",
      "created_at": "2026-05-28T10:19:20.615Z"
    }
  ],
  "total_count": 2,
  "limit": 30,
  "offset": 0
}
        
        # Моковый ответ для фасетов
        self.mock_b2b_facets_response = {
            'category_id': self.category_id,
            'facets': [
                {
                    'name': 'brand',
                    'values': [
                        {'value': 'Apple', 'count': 124},
                        {'value': 'Samsung', 'count': 98},
                        {'value': 'Xiaomi', 'count': 76}
                    ]
                },
                {
                    'name': 'color',
                    'values': [
                        {'value': 'черный', 'count': 60},
                        {'value': 'белый', 'count': 40}
                    ]
                }
            ]
        }

    # ==================== Тесты для /api/v1/catalog/products ====================

    def test_catalog_returns_filtered_sorted_products(self):
        """
        Happy path: фильтрация по категории и бренду + сортировка по цене.
        Проверяет, что B2C корректно проксирует запрос к B2B и трансформирует ответ.
        """
        # Подготовка мока для B2BClient._call_b2b
        with patch.object(B2BClient, '_call_b2b') as mock_b2b:
            mock_b2b.side_effect = [self.mock_b2b_products_response,self.mock_b2b_products_data_response]
            
            # Запрос с фильтрами и сортировкой
            url = reverse('app:products-list')  # /api/v1/catalog/products
            response = self.client.get(url, {
                'filter[category_id]': self.category_id,
                'filter[brand]': 'Apple',
                'filter[price_min]': '10000',
                'filter[price_max]': '15000000',
                'sort': 'price_asc',
                'limit': 30,
                'offset': 0,
                'q': 'iphone'
            })
            
            # Assert: статус и структура ответа
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json()
            
            self.assertIn('items', data)
            self.assertIn('total_count', data)
            self.assertIn('limit', data)
            self.assertIn('offset', data)
            
            self.assertEqual(data['total_count'], 2)
            self.assertEqual(data['limit'], 30)
            self.assertEqual(data['offset'], 0)
            self.assertEqual(len(data['items']), 2)
            
            # Assert: трансформация полей B2B → B2C
            product = data['items'][0]
            self.assertEqual(product['id'], self.product_id)
            self.assertEqual(product['name'], 'Iphone 15 Black 256GB')  # B2B: title → B2C: name
            self.assertEqual(product['min_price'], 65000)  # вычислено из SKU
            self.assertTrue(product['has_stock'])  # active_quantity > 0
            self.assertIn('images', product)
            
            # Assert: B2BClient вызван с правильными параметрами
            call_kwargs = mock_b2b.call_args_list[0][0][1]
            self.assertEqual(call_kwargs['filters[category_id]'][0], self.category_id)
            self.assertEqual(call_kwargs['filters[brand]'][0], 'Apple')
            self.assertEqual(call_kwargs['filters[price_min]'][0], '10000')
            self.assertEqual(call_kwargs['filters[price_max]'][0], '15000000')
            self.assertEqual(call_kwargs['sort'], 'price_asc')
            self.assertEqual(call_kwargs['limit'], 30)
            self.assertEqual(call_kwargs['offset'], 0)
            self.assertEqual(call_kwargs['search'], 'iphone')
            

    def test_catalog_empty_category_returns_200_with_empty_items(self):
        """
        Edge case: категория существует, но товаров нет.
        Должен вернуться 200 с пустым списком items.
        """
        empty_response = {
            'items': [],
            'total_count': 0,
            'limit': 20,
            'offset': 0
        }
        
        with patch.object(B2BClient, '_call_b2b') as mock_b2b:
            mock_b2b.return_value = empty_response
            
            url = reverse('app:products-list')
            response = self.client.get(url, {'filter[category_id]': self.category_id})
            
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json()
            self.assertEqual(data['items'], [])
            self.assertEqual(data['total_count'], 0)

    def test_catalog_no_filters_returns_default_sorted_products(self):
        """
        Запрос без фильтров должен вернуть товары с сортировкой по умолчанию (popularity).
        """
        with patch.object(B2BClient, '_call_b2b') as mock_b2b:
            #сначала запрос для получения товаров, затем запрос для получения информации о has_stock
            mock_b2b.side_effect = [self.mock_b2b_products_response,self.mock_b2b_products_data_response]
            
            url = reverse('app:products-list')
            response = self.client.get(url)  # без параметров
            
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            
            # Проверка, что sort передан как 'popularity' (default из b2c.yaml)
            call_kwargs = mock_b2b.call_args_list[0][0][1]
            # в спеке b2b параметр sort ожидает: Available values : price_asc, price_desc, created_desc, popular
            # хотя в спеке b2c принимаются другие значения этого же параметра Available values : price_asc, price_desc, popularity, new
            # поэтому запрос к b2b именно с popular
            self.assertEqual(call_kwargs['sort'], 'popular') 

    # ==================== Тесты валидации ====================

    def test_invalid_sort_returns_400(self):
        """
        Невалидный параметр sort должен вернуть 400 с перечислением допустимых значений.
        Соответствует требованию: invalid_sort_returns_400
        """
        url = reverse('app:products-list')
        response = self.client.get(url, {'sort': 'invalid_sort_value'})
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        
        self.assertEqual(data['code'], "INVALID_REQUEST")
        self.assertIn('message', data)
        # Сообщение должно содержать допустимые значения для отладки
        message = data['message']
        self.assertTrue(
            any(val in message for val in ['price_asc', 'price_desc', 'popularity', 'new']),
            f"Expected allowed sort values in error message, got: {data['message']}"
        )

    def test_invalid_limit_returns_400(self):
        """
        limit > 100 или limit < 1 должен вернуть 400.
        """
        url = reverse('app:products-list')
        
        # Слишком большой limit
        response = self.client.get(url, {'limit': 150})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        # Отрицательный limit
        response = self.client.get(url, {'limit': -5})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_offset_returns_400(self):
        """
        offset < 0 должен вернуть 400.
        """
        url = reverse('app:products-list')
        response = self.client.get(url, {'offset': -10})
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()['code'], "INVALID_REQUEST")

    # ==================== Тесты ошибок B2B ====================

    def test_b2b_unavailable_returns_502(self):
        """
        При недоступности B2B (ConnectionError) должен вернуться 502/503.
        Соответствует требованию: b2b_unavailable_returns_502
        """
        with patch.object(B2BClient, '_call_b2b') as mock_b2b:
            # Имитация ошибки подключения к B2B
            from app.exceptions import B2BUnavailableError
            mock_b2b.side_effect = B2BUnavailableError('B2B service unavailable')
            
            url = reverse('app:products-list')
            response = self.client.get(url)
            
            # Допускаем 502 или 503 в зависимости от реализации
            self.assertIn(response.status_code, [
                status.HTTP_502_BAD_GATEWAY,
                status.HTTP_503_SERVICE_UNAVAILABLE
            ])
            
            data = response.json()
            self.assertIn('code', data)
            self.assertIn('message', data)
            # Сообщение должно быть понятным для пользователя
            self.assertTrue(
                any(phrase in data['message'].lower() for phrase in ['недоступен', 'попробуйте позже', 'temporarily']),
                f"Expected user-friendly error message, got: {data['message']}"
            )

    def test_b2b_category_not_found_returns_404(self):
        """
        Если B2B вернул 404 (категория не найдена), B2C должен проксировать 404.
        """
        with patch.object(B2BClient, '_call_b2b_by_func') as mock_b2b:
            # B2BClient должен выбрасывать ValueError для 404
            real_response = requests.Response()
            real_response.status_code = 404
            real_response.reason = "Internal Server Error"
            real_response.url = "https://api.example.com/data"
            real_response._content = b'{"detail": "server crashed"}'
            real_response.encoding = 'utf-8'

            mock_b2b.return_value = real_response
            
            url = reverse('app:products-list')
            response = self.client.get(url, {'filter[category_id]': 'non-existent-uuid'})
            
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
            data = response.json()
            self.assertEqual(data['code'], 'NOT_FOUND')

    # ==================== Тесты для /api/v1/catalog/facets ====================

    def test_facets_return_counts_per_filter_value(self):
        """
        Фасеты должны возвращать корректные подсчёты для каждого значения фильтра.
        Соответствует требованию: facets_return_counts_per_filter_value
        """
        with patch.object(B2BClient, '_call_b2b') as mock_facets:
            mock_facets.return_value = self.mock_b2b_facets_response
            
            # Предполагаем, что эндпоинт /api/v1/catalog/facets добавлен в urls.py
            url = reverse('app:facets')  # reverse('app:facets') если добавите name
            response = self.client.get(url, {
                'category_id': self.category_id,
                'filter[brand]': 'Apple'
            })
            
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json()
            
            self.assertIn('facets', data)
            self.assertEqual(data['category_id'], self.category_id)
            
            # Проверка структуры фасетов
            facets = {f['name']: f for f in data['facets']}
            self.assertIn('brand', facets)
            self.assertIn('color', facets)
            
            # Проверка подсчётов для бренда
            brand_values = {v['value']: v['count'] for v in facets['brand']['values']}
            self.assertEqual(brand_values['Apple'], 124)
            self.assertEqual(brand_values['Samsung'], 98)
            
            # Проверка, что B2B вызван с правильными параметрами
            mock_facets.assert_called_once()
            call_kwargs = mock_facets.call_args[0][1]
            self.assertEqual(str(call_kwargs['category_id']), self.category_id)
            self.assertEqual(call_kwargs['filters[brand]'][0], 'Apple')

    def test_facets_without_filters_returns_all_counts(self):
        """
        Запрос фасетов без фильтров должен вернуть подсчёты для всех значений.
        """
        with patch.object(B2BClient, '_call_b2b') as mock_facets:
            mock_facets.return_value = self.mock_b2b_facets_response
            
            url = reverse('app:facets')
            response = self.client.get(url, {'category_id': self.category_id})
            
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json()
            
            # Должны вернуться все значения фасетов
            brand_facet = next(f for f in data['facets'] if f['name'] == 'brand')
            self.assertEqual(len(brand_facet['values']), 3)  # Apple, Samsung, Xiaomi

    def test_facets_b2b_unavailable_returns_empty_facets(self):
        """
        При недоступности B2B фасеты должны вернуть пустой список (не блокировать каталог).
        """
        with patch.object(B2BClient, '_call_b2b') as mock_facets:
            from app.exceptions import B2BUnavailableError
            mock_facets.side_effect = B2BUnavailableError('B2B unavailable')
            
            url = reverse('app:facets')
            # неизвестная категория, чтобы с ней не было кеша
            response = self.client.get(url, {'category_id': '123e4567-e89b-12d3-a456-426614174002'}) 
            
            # Фасеты не критичны — возвращаем 200 с пустыми данными
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json()
            self.assertEqual(data['facets'], [])

    def test_facets_missing_category_id_returns_400(self):
        """
        Запрос фасетов без category_id должен вернуть 400.
        """
        url = reverse('app:facets')
        response = self.client.get(url)  # без category_id
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        self.assertEqual(data['code'], 'INVALID_REQUEST')



