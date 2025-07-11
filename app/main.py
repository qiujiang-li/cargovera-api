from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import users, auth, accounts, wallet, addresses, webstores, labels, orders,transactions, payments,admin, health
from app.db.session import init_db
from app.handlers.exception_handlers import init_exception_handlers
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
# Optional: add a console handler if none exists
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)



app = FastAPI(title="Cargovera API Service")

origins = [
    "http://localhost:5173",  # or wherever your frontend runs
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "https://www.cargovera.com"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,           # or ["*"] for all origins (less secure)
    allow_credentials=True,
    allow_methods=["*"],             # must include "OPTIONS"
    allow_headers=["*"],             # allow custom headers like Authorization
)


#init exception handlers
init_exception_handlers(app)

app.include_router(users.router, prefix="/users", tags=["Users"])
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(addresses.router, prefix="/addresses", tags=["Addresses"])
app.include_router(webstores.router, prefix="/webstores", tags=["Webstores"])
app.include_router(labels.router, prefix="/labels", tags=["Labels"])
app.include_router(orders.router, prefix="/orders", tags=["Orders"])
app.include_router(transactions.router,prefix="/transactions", tags=["Transactions"])
app.include_router(payments.router,prefix="/payments", tags=["Payments"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])
app.include_router(health.router, prefix="/health", tags=["Health"])

# app.include_router(labels.router, prefix="/labels", tags=["Shipping"])


@app.on_event("startup")
async def startup():
    await init_db()

