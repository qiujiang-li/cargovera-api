from typing import TypeVar, Generic, List, Optional, Any
from pydantic import BaseModel
from datetime import datetime
from enum import Enum
import json
import base64
from fastapi import HTTPException
from uuid import UUID
# Pydantic models
class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"

class PaginationInfo(BaseModel):
    current_page: Optional[int] = None
    total_pages: Optional[int] = None
    total_items: Optional[int] = None
    items_per_page: int
    has_next: bool
    has_previous: bool
    next_cursor: Optional[str] = None
    previous_cursor: Optional[str] = None

class PaginationLinks(BaseModel):
    first: Optional[str] = None
    previous: Optional[str] = None
    next: Optional[str] = None
    last: Optional[str] = None

from typing import TypeVar, Generic, List

# Define a generic type variable
T = TypeVar('T')  # T can be any Pydantic model (e.g., ProductResponse, UserResponse, etc.)

class PaginatedResponse(BaseModel,Generic[T]):
    data: List[T]
    pagination: PaginationInfo
    links: Optional[PaginationLinks] = None

class CursorData(BaseModel):
    id: UUID
    created_at: datetime
    sort_field: Optional[str] = None
    sort_value: Optional[Any] = None
