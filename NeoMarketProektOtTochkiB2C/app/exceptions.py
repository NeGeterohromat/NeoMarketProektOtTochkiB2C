from rest_framework.response import Response
from rest_framework import status

def error_response(
    code: str,
    message: str,
    status: int = status.HTTP_400_BAD_REQUEST,
    details: dict | None = None
) -> Response:
    """
    Возвращает ответ в формате OpenAPI Error.
    Соответствует components/schemas/Error из b2c.yaml/b2b.yaml
    """
    payload = {"code": code, "message": message}
    if details is not None:
        payload["details"] = details
    return Response(payload, status=status)

class B2BUnavailableError(Exception):
    pass

class BlockedProductError(Exception):
    pass

class ReserveFailedError(Exception):
    def __init__(self,failed_items):
        self.failed_items=failed_items

class CheckoutValidationError(Exception):
    pass