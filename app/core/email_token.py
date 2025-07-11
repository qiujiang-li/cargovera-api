from itsdangerous import URLSafeTimedSerializer
from app.core.config import settings

serializer = URLSafeTimedSerializer(settings.jwt_secret)

EMAIL_TOKEN_SALT = "email-confirm"
RESET_PASSWORD_SALT = "password-reset"

def generate_email_token(email: str) -> str:
    return serializer.dumps(email, salt=EMAIL_TOKEN_SALT)

def verify_email_token(token: str, max_age: int = 3600) -> str:
    return serializer.loads(token, salt=EMAIL_TOKEN_SALT, max_age=max_age)

def generate_reset_token(email: str) -> str:
    return serializer.dumps(email, salt=RESET_PASSWORD_SALT)

def verify_reset_token(token: str, max_age: int = 3600) -> str:
    return serializer.loads(token, salt=RESET_PASSWORD_SALT, max_age=max_age)