from pydantic_settings import BaseSettings
from typing import Dict, Optional
import os

class Settings(BaseSettings):
    # these must be set in the environment
    database_url: str
    jwt_secret: str

    # Optional Settings with default values
    fedex_api_key: str = ""
    amazon_credentials: Dict = {}

    email_from: str = "noreply@cargovera.com"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    smtp_username: str = "cargovera.com"
    # these must be set in the environment
    smtp_password: str 

    # Add more environment variables as needed
    app_name: str = "https://www.cargovera.com"
    api_host: str = "https://api.cargovera.com"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

settings = Settings()

