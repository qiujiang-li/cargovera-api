# exceptions.py
from decimal import Decimal

class BusinessLogicException(Exception):
    """Base class for business-related exceptions."""
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(self.detail)
    pass

class InsufficientBalanceException(BusinessLogicException):
    def __init__(self, balance: Decimal, required: Decimal):
        self.balance = balance
        self.required = required
        super().__init__(
            status_code=400, 
            detail=f"Insufficient balance: {balance} available, {required} required"
        )

class NegativeAmountException(BusinessLogicException):
    def __init__(self, amount: Decimal):
        super().__init__(
            status_code=400,
            detail=f"Negative amount {amount} not accepted"
        )

class UserNotFoundException(BusinessLogicException):
    def __init__(self, user_id: str):
        super().__init__(
            status_code=404,
            detail=f"User {user_id} not found"
        )

class PaymentNotFoundException(BusinessLogicException):
    def __init__(self, message: str):
        super().__init__(
            status_code=404,
            detail=message
        )

class UnSupportedCarrierException(BusinessLogicException):
    def __init__(self, carrier: str):
        super().__init__(status_code=400, detail=f"Unsupported carrier: {carrier}")

class RateNotAvailableException(BusinessLogicException):
    def __init__(self, service_type: str):
        super().__init__(status=400, detail=f"No rates available for requested service type: {service_type}")

class LabelValidationException(BusinessLogicException):
    def __init__(self, detail: str):
        super().__init__(status_code=400, detail=detail)

class OrderNotFoundException(BusinessLogicException):
    def __init__(self, detail: str):
        super().__init__(status_code=404, detail=detail)

class InconsistentStatusException(BusinessLogicException):
    def __init__(self, detail: str):
        super().__init__(status_code=400, detail=detail)


class ResourceConflictException(Exception):
    def __init__(self,status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(self.detail)


class DatabaseException(Exception):
    """Base class for database-related exceptions."""
    def __init__(self,status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(self.detail)

class DatabaseConstraintException(DatabaseException):
    def __init__(self, detail: str):
        super().__init__(status_code=409, detail=detail)



class ExternalServiceException(Exception):
    """Base class for external service-related exceptions."""
    def __init__(self, detail: str, status_code: int = 500):
        self.status_code = status_code
        self.detail = detail
        super().__init__(self.detail)

class ExternalServiceClientError(ExternalServiceException):
    def __init__(self, message: str):
        super().__init__(status_code=400, detail=message)

class ExternalServiceServerError(ExternalServiceException):
    """Exception raised when there is an issue connecting to the external service."""
    def __init__(self, message: str):
        super().__init__(status_code=502, detail=message)
