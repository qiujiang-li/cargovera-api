# logging_config.py
import logging
import os
from logging.handlers import RotatingFileHandler

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_FILE = "app.log"

def setup_logging():
    # Create handlers
    console_handler = logging.StreamHandler()
    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=10_000_000, backupCount=3
    )

    # Set levels
    console_handler.setLevel(logging.DEBUG)
    file_handler.setLevel(logging.DEBUG)

    # Create formatter and add to handlers
    formatter = logging.Formatter(LOG_FORMAT)
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    # Get the root logger and add handlers
    root_logger = logging.getLogger()
    
    if os.getenv("DEBUG", "false").lower() == "true":
        root_logger.setLevel(logging.DEBUG)
    else:
        root_logger.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Optionally: adjust uvicorn loggers to propagate to root logger
    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_logger.propagate = True
    uvicorn_error_logger = logging.getLogger("uvicorn.error")
    uvicorn_error_logger.propagate = True
    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    uvicorn_access_logger.propagate = True
    uvicorn_access_logger.setLevel(logging.WARNING)

    sqlalchemy_engine_logger = logging.getLogger("sqlalchemy.engine")
    sqlalchemy_engine_logger.setLevel(logging.WARNING)
    sqlalchemy_engine_logger.handlers = []
    sqlalchemy_engine_logger.propagate = False
