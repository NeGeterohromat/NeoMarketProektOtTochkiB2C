"""
Definition of views.
"""

from datetime import datetime
from django.shortcuts import render
from django.http import HttpRequest

def home(request):
    """Renders the home page."""
    assert isinstance(request, HttpRequest)
    return render(
        request,
        'app/index.html',
        {
            'title':'Home Page',
            'year':datetime.now().year,
        }
    )

def contact(request):
    """Renders the contact page."""
    assert isinstance(request, HttpRequest)
    return render(
        request,
        'app/contact.html',
        {
            'title':'Contact',
            'message':'Your contact page.',
            'year':datetime.now().year,
        }
    )

def about(request):
    """Renders the about page."""
    assert isinstance(request, HttpRequest)
    return render(
        request,
        'app/about.html',
        {
            'title':'About',
            'message':'Your application description page.',
            'year':datetime.now().year,
        }
    )

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.exceptions import ValidationError
from .services import B2BClient
from .serializers import CatalogListQuerySerializer, FacetsQuerySerializer
from .exceptions import B2BUnavailableError, error_response

ALLOWED_SORT_VALUES = ['price_asc', 'price_desc', 'popularity', 'new']

class CatalogProductsView(APIView):
    """GET /api/v1/catalog/products — листинг товаров с фильтрами"""
    
    def get(self, request):
        # 1. Валидация параметров
        serializer = CatalogListQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            # 2. Валидация sort (дополнительная, т.к. enum в serializer может не покрыть всё)
            if request.query_params.get('sort') and request.query_params.get('sort') not in ALLOWED_SORT_VALUES:
                return error_response(
                    code="INVALID_REQUEST",
                    message=f'Invalid sort parameter. Allowed: {", ".join(ALLOWED_SORT_VALUES)}',
                    status=status.HTTP_400_BAD_REQUEST
                )

            return error_response(
                code="INVALID_REQUEST",
                message=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        params = serializer.validated_data
        
        filters = {}
        for key, value in request.GET.items():
            if key.startswith('filter[') and key.endswith(']'):
                filter_key = key[7:-1]  # Извлекаем brand из filter[brand]
                filters[filter_key] = value
        
        # 3. Вызов B2B
        b2b_client = B2BClient()
        try:
            result = b2b_client.get_public_products(
                category_id=params.get('category_id'),
                filters=filters,  # deepObject: filter[price_min]=...
                sort=params.get('sort'),
                limit=params.get('limit', 20),
                offset=params.get('offset', 0),
                search=params.get('q')
            )
            # Для async: result = await b2b_client.get_public_products(...)
            return Response(result, status=status.HTTP_200_OK)
            
        except ValueError as e:  # Категория не найдена
            return error_response(code='NOT_FOUND', message=str(e), status=status.HTTP_404_NOT_FOUND)
        except B2BUnavailableError:
            return error_response(
                code='B2B_UNAVAILABLE',
                message='Каталог временно недоступен, попробуйте позже',
                status=status.HTTP_502_BAD_GATEWAY  # или 503
            )
        except Exception as e:
            # Логирование ошибки
            print('vnkgnv',e)
            return error_response(code='INTERNAL_ERROR', message='Internal server error', status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CatalogFacetsView(APIView):
    """GET /api/v1/catalog/facets — подсчёт товаров по фильтрам
    
    ⚠️ Этот эндпоинт отсутствует в b2c.yaml — предлагается добавить:
    /api/v1/catalog/facets?category_id=uuid&filter[brand]=Apple
    """
    
    def get(self, request):
        serializer = FacetsQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return error_response(
                code='INVALID_REQUEST',
                message=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        params = serializer.validated_data
        b2b_client = B2BClient()

        filters = {}
        for key, value in request.GET.items():
            if key.startswith('filter[') and key.endswith(']'):
                filter_key = key[7:-1]  # Извлекаем brand из filter[brand]
                filters[filter_key] = value

        try:
            facets = b2b_client.get_facets(
                category_id=params['category_id'],
                filters=filters
            )
            return Response(facets, status=status.HTTP_200_OK)
        except B2BUnavailableError:
            # Фасеты не критичны — возвращаем пустые, каталог работает
            return Response({'facets': []}, status=status.HTTP_200_OK)
