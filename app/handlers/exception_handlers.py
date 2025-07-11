from fastapi import Request, FastAPI
from fastapi.responses import JSONResponse
from app.core.exceptions import BusinessLogicException, DatabaseException, ResourceConflictException, ExternalServiceException

async def business_logic_exception_handler(request: Request, exc: BusinessLogicException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc)}
    )

async def database_exception_handler(request: Request, exc: DatabaseException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc)}
    )

async def resource_conflict_exception_handler(request: Request, exc: ResourceConflictException):
    return JSONResponse(
        status_code=409,
        content={"detail": str(exc)}
    )

async def external_service_exception_handler(request: Request, exc: ExternalServiceException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc)}
    )

def init_exception_handlers(app: FastAPI):
    app.add_exception_handler(BusinessLogicException, business_logic_exception_handler)
    app.add_exception_handler(DatabaseException, database_exception_handler)
    app.add_exception_handler(ResourceConflictException, resource_conflict_exception_handler)
    app.add_exception_handler(ExternalServiceException, external_service_exception_handler)