from rest_framework import serializers

class CatalogFilterSerializer(serializers.Serializer):
    """Валидация deepObject-фильтров: filter[price_min]=10000&filter[brand]=Apple"""
    category_id = serializers.UUIDField(required=False, allow_null=True)
    price_min = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    price_max = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    seller_id = serializers.UUIDField(required=False, allow_null=True)
    # Динамические атрибуты: color, brand, memory и т.д.
    attributes = serializers.DictField(
        child=serializers.CharField(allow_blank=True),
        required=False,
        allow_null=True
    )
    
    def to_internal_value(self, data):
        # Преобразуем flat-параметры filter[field]=value в dict
        result = {}
        for key, value in data.items():
            if key.startswith('filter[') and key.endswith(']'):
                field_name = key[7:-1]  # Извлекаем имя поля
                result[field_name] = value
            else:
                result[key] = value
        return super().to_internal_value(result)


class CatalogListQuerySerializer(serializers.Serializer):
    """Параметры запроса к /api/v1/catalog/products"""
    limit = serializers.IntegerField(min_value=1, max_value=100, default=20, required=False)
    offset = serializers.IntegerField(min_value=0, default=0, required=False)
    q = serializers.CharField(max_length=200, required=False, allow_blank=True)
    sort = serializers.ChoiceField(
        choices=['price_asc', 'price_desc', 'popularity', 'new'],
        default='popularity',
        required=False
    )
    filter = CatalogFilterSerializer(required=False, source='*')  # deepObject


class FacetsQuerySerializer(serializers.Serializer):
    """Параметры для /api/v1/catalog/facets"""
    category_id = serializers.UUIDField(required=True)
    filter = CatalogFilterSerializer(required=False, source='*')

class ProductDetailQuerySerializer(serializers.Serializer):
    """Параметры для /api/v1/catalog/products{id}"""
    sku = serializers.UUIDField(required=False)