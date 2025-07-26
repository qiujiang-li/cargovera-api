# Core pagination service

from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload
from sqlalchemy.inspection import inspect
from app.schemas.pagination import PaginatedResponse, SortOrder, PaginationLinks, PaginationInfo
from app.schemas.pagination import CursorData
from sqlalchemy.orm import aliased
from fastapi import HTTPException
import json
import base64
from datetime import datetime
from sqlalchemy import or_, and_, desc, asc, select, func,cast, String
from typing import Dict, Any, List, TypeVar, Type, Tuple
from pydantic import BaseModel
from app.models.inventory import Inventory
import logging

# Generic type for the output schema classes
T = TypeVar('T', bound=BaseModel)
logger = logging.getLogger(__name__)
# Utility functions
def encode_cursor(cursor_data: CursorData) -> str:
    """Encode cursor data to base64 string"""
    cursor_dict = {
        "id": cursor_data.id,
        "created_at": cursor_data.created_at.isoformat(),
        "sort_field": cursor_data.sort_field,
        "sort_value": cursor_data.sort_value
    }
    cursor_json = json.dumps(cursor_dict)
    return base64.b64encode(cursor_json.encode()).decode()

def decode_cursor(cursor: str) -> CursorData:
    """Decode base64 cursor to cursor data"""
    try:
        cursor_json = base64.b64decode(cursor.encode()).decode()
        cursor_dict = json.loads(cursor_json)
        return CursorData(
            id=cursor_dict["id"],
            created_at=datetime.fromisoformat(cursor_dict["created_at"]),
            sort_field=cursor_dict.get("sort_field"),
            sort_value=cursor_dict.get("sort_value")
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid cursor format")


class PaginationService:
    def __init__(self, db: Session):
        self.db = db

    async def paginate_like(
    self,
    model_class,
    output_schema: Type[T],
    column_name: str,
    query_str: str,
    page: int,
    limit: int = 10

    ) -> PaginatedResponse:

        # Count total items
        column = getattr(model_class, column_name)
        condition = or_(
            func.lower(column).ilike(f"%{query_str}%"),
            func.similarity(func.lower(column), query_str) > 0.03
        )
        count_stmt = select(func.count()).select_from(
            select(model_class)
            .where(condition)
            .subquery()
        )
        count_result = await self.db.execute(count_stmt)
        total_items = count_result.scalar_one()
        print(total_items)

        total_pages = (total_items + limit - 1) // limit
        # Validate page number
        if page is None or page < 1:
            page = 1
        elif page > total_pages and total_pages > 0:
            raise HTTPException(status_code=404, detail="Page not found")

        # Apply offset and limit
        offset = (page - 1) * limit

        # Primary: pg_trgm similarity
        stmt = (
            select(model_class)
            .where(condition)
            .order_by(func.similarity(column, query_str).desc())
            .offset(offset)
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        items = result.scalars().all()

        pagination = PaginationInfo(
            current_page=page,
            total_pages=total_pages,
            total_items=total_items,
            items_per_page=limit,
            has_next=page < total_pages,
            has_previous=page > 1
        )
        
        #links = self._build_offset_links(page, total_pages, limit, sort_by, sort_order)
        
        return PaginatedResponse(data=items, pagination=pagination, links=None)
        
    def _get_column(self,model_class, field_path: str):
        """Supports dot-paths like 'product.name'."""
        parts = field_path.split('.')
        current = model_class
        for i, part in enumerate(parts):
            try:
                current = getattr(current, part)
            except AttributeError:
                raise ValueError(f"Invalid field path: {field_path}")
            
            if i == len(parts) - 1:
                return current

            # Dive into related model if it's a relationship
            if hasattr(current, "property") and hasattr(current.property, "mapper"):
                current = current.property.mapper.class_
            else:
                raise ValueError(f"Cannot resolve relationship for: {'.'.join(parts[:i+1])}")

        return current

    def _build_eager_loads(self, model: Any, paths: List[str]):
        loaders = []
        seen_paths = set()

        for path in paths:
            if path in seen_paths:
                continue  # Avoid duplicate loaders
            seen_paths.add(path)

            attrs = path.split(".")
            loader = None
            current_model = model

            for i, attr in enumerate(attrs):
                try:
                    attr_class_attr = getattr(current_model, attr)
                except AttributeError:
                    raise ValueError(f"Invalid eager load path '{path}': '{attr}' not found on {current_model.__name__}")
                if i == 0:
                    loader = selectinload(attr_class_attr)
                else:
                    loader = loader.selectinload(attr_class_attr)
                # Navigate into the relationship’s model for the next attr
                rel = attr_class_attr.property
                current_model = rel.mapper.class_
            loaders.append(loader)
        return loaders
    
    def _apply_joins(self, stmt, model_class, column_paths):
        joined_paths = {}         # e.g. "inventory.owner" -> aliased model or real model
        table_name_counts = {}    # to track multiple joins to the same table

        for path in column_paths:
            parts = path.split(".")
            if len(parts) < 2:
                continue

            current_model = model_class
            join_path = []

            for i in range(len(parts) - 1):  # skip final column (not a relationship)
                rel_name = parts[i]
                join_path.append(rel_name)
                path_key = ".".join(join_path)

                # If already joined, use the cached model
                if path_key in joined_paths:
                    current_model = joined_paths[path_key]
                    continue

                attr = getattr(current_model, rel_name)
                rel_model = attr.property.mapper.class_
                table_name = rel_model.__tablename__

                # Count how many times this table has been joined
                table_name_counts[table_name] = table_name_counts.get(table_name, 0) + 1

                if table_name_counts[table_name] > 1:
                    # Alias required to prevent duplicate join to same table
                    aliased_model = aliased(rel_model)
                    aliased_attr = attr.of_type(aliased_model)
                    stmt = stmt.join(aliased_attr)
                    current_model = aliased_model
                else:
                    # Standard join without aliasing
                    stmt = stmt.join(attr)
                    current_model = rel_model

                # Store the model (aliased or not) used for this join path
                joined_paths[path_key] = current_model

        return stmt, joined_paths

    def _resolve_attr_path(self, model_class, path: str, joined_paths: Dict[str, Any]):
        if not isinstance(path, str):
            raise TypeError(f"path must be str, got {type(path)}")

        parts = path.split(".")
        current_model = model_class
        attr = None
        current_path = []

        for i, part in enumerate(parts):
            current_path.append(part)
            path_key = ".".join(current_path)

            # Use joined_paths to get the correct model if already joined
            if path_key in joined_paths:
                current_model = joined_paths[path_key]
                attr = current_model  # alias or mapped class
                continue

            try:
                attr = getattr(current_model, part)
            except AttributeError:
                raise AttributeError(f"{current_model} has no attribute '{part}' (while resolving '{path}')")

            # If this is a relationship, move to the related model
            if hasattr(attr, "property") and hasattr(attr.property, "mapper"):
                current_model = attr.property.mapper.class_
        return attr

    def _build_search_condition(self, model_class, search_columns, query_str, joined_paths: Dict[str, Any],language="english"):
        if not query_str or not search_columns:
            return None

        # Resolve columns with nested support
        columns = [self._resolve_attr_path(model_class, col, joined_paths) for col in search_columns]

        # Build tsvector
        tsvector = func.to_tsvector(
            language,
            func.concat_ws(' ', *[cast(col, String) for col in columns])
        )

        tsquery = func.websearch_to_tsquery(language, query_str)

        # Full-text condition
        fulltext_condition = tsvector.op('@@')(tsquery)

        # Similarity conditions (fallback fuzzy matching)
        similarity_conditions = [
            func.similarity(func.lower(cast(col, String)), query_str.lower()) > 0.03
            for col in columns
        ]
        return or_(fulltext_condition, *similarity_conditions)

    async def paginate_with_full_search(
        self, 
        model_class,
        output_schema: Type[T],
        query_str: str,
        search_columns: List[str],
        page: int,
        limit: int,
        sort_by: str, 
        sort_order: SortOrder,
        rank: bool = True,
        eager_load: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None,
        language: str = "english"): 
        offset = (page - 1) * limit

        stmt = select(model_class)

        #if join needed
        # Apply joins for search and nested filters
        all_paths = (search_columns or []) + list(filters.keys() if filters else [])
        stmt, joined_paths = self._apply_joins(stmt, model_class, all_paths)
        # Apply filters
        logger.info(f"Filters type: {type(filters)}")
        logger.info(f"Filters content: {filters}")
        if filters:
            for path, value in filters.items():
                # Pass the path string and the joined_paths dict separately
                attr = self._resolve_attr_path(model_class, path, joined_paths)
                stmt = stmt.where(attr == value)
        conditions = []

        if query_str:
            search_condition = self._build_search_condition(
            model_class=model_class,
            search_columns=search_columns,
            query_str=query_str,
            joined_paths=joined_paths,
            language=language)
            conditions.append(search_condition)

        # Eager load relationships
        load_options = self._build_eager_loads(model_class, eager_load)
        if load_options:
            stmt = stmt.options(*load_options)


        # if filters:
        #     for field, value in filters.items():
        #         if hasattr(model_class, field) and value is not None:
        #             column = getattr(model_class, field)
        #             if isinstance(value, dict):
        #                 # Handle range filters like {"gte": 100, "lte": 500}
        #                 if "gte" in value:
        #                     conditions.append(column >= value['gte'])
        #                 if "lte" in value:
        #                     conditions.append(column <= value['lte'])
        #                 if "eq" in value:
        #                     conditions.append(column == value['eq'])
        #                 if "like" in value:
        #                     conditions.append(column.ilike(f"%{value['like']}%"))

        #             else:
        #                 # Direct equality filter
        #                 conditions.append(column == value)
        
        stmt = stmt.where(and_(*conditions))

        # Apply sorting
        sort_column = getattr(model_class, sort_by, getattr(model_class, "created_at", getattr(model_class, "id")))
        if sort_order == SortOrder.desc:
            stmt = stmt.order_by(desc(sort_column))
        else:
            stmt = stmt.order_by(asc(sort_column))

        # if rank:
        #     rank_expr = func.ts_rank(tsvector, tsquery)
        #     stmt = stmt.order_by(rank_expr.desc())
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.db.execute(count_stmt)
        total_items = count_result.scalar_one()

        
        stmt = stmt.offset(offset).limit(limit)
        result = await self.db.execute(stmt)
        items = result.scalars().all()

        total_pages = (total_items + limit - 1) // limit
        
        pagination = PaginationInfo(
                current_page=page,
                total_pages=total_pages,
                total_items=total_items,
                items_per_page=limit,
                has_next=page < total_pages,
                has_previous=page > 1
            )
        
            #links = self._build_offset_links(page, total_pages, limit, sort_by, sort_order)
          # Build response (generic - works with any model)
        data = [output_schema.from_orm(item) for item in items] 
        return PaginatedResponse(data=data, pagination=pagination, links=None)


    
    async def paginate(
        self,
        model_class,
        output_schema: Type[T],
        page: Optional[int] = None,
        cursor: Optional[str] = None,
        limit: int = 20,
        sort_by: str = "created_at",
        sort_order: SortOrder = SortOrder.desc,
        filters: Optional[Dict[str, Any]] = None,
    ) -> PaginatedResponse:
        """
        Generic pagination method that works with any SQLAlchemy model.
        
        Args:
            model_class: SQLAlchemy model class to paginate
            page: Page number for offset-based pagination
            cursor: Cursor for cursor-based pagination
            limit: Number of items per page
            sort_by: Field name to sort by
            sort_order: Sort order (asc/desc)
            filters: Dictionary of field:value filters
            search_fields: List of fields to search in
            search_query: Search term to apply across search_fields
        """
        
        # Build base query
        where_filters = []
        # Apply filters
        if filters:
            for field, value in filters.items():
                if hasattr(model_class, field) and value is not None:
                    column = getattr(model_class, field)
                    if isinstance(value, dict):
                        # Handle range filters like {"gte": 100, "lte": 500}
                        if "gte" in value:
                            where_filters.append(column >= value['gte'])
                        if "lte" in value:
                            where_filters.append(column <= value['lte'])
                        if "eq" in value:
                            where_filters.append(column == value['eq'])
                        if "like" in value:
                            where_filters.append(column.ilike(f"%{value['like']}%"))

                    else:
                        # Direct equality filter
                        where_filters.append(column == value)
        
        # Determine pagination strategy
        if cursor:
            return await self._cursor_paginate(where_filters, model_class, output_schema, cursor, limit, sort_by, sort_order)
        elif page:
            return await self._offset_paginate(where_filters, model_class, output_schema, page, limit, sort_by, sort_order)
        else:
            # Default to cursor-based for better performance
            return await self._offset_paginate(where_filters, model_class, output_schema, None, limit, sort_by, sort_order)

    async def _offset_paginate(
            self, 
            where_filters, 
            model_class,
            output_schema,
            page: int, 
            limit: int, 
            sort_by: str, 
            sort_order: SortOrder
        ) -> PaginatedResponse:
            
            # Apply sorting
            sort_column = getattr(model_class, sort_by, getattr(model_class, "created_at", getattr(model_class, "id")))
            if sort_order == SortOrder.desc:
                query = select(model_class).where(*where_filters).order_by(desc(sort_column))
            else:
                query = select(model_class).where(*where_filters).order_by(asc(sort_column))

            count_query = select(func.count()).select_from(select(model_class).where(*where_filters).subquery())
            total_result = await self.db.execute(count_query)
            total_items = total_result.scalar()
            total_pages = (total_items + limit - 1) // limit
            # Validate page number
            if page is None or page < 1:
                page = 1
            elif page > total_pages and total_pages > 0:
                raise HTTPException(status_code=404, detail="Page not found")

            # Apply offset and limit
            offset = (page - 1) * limit
            query = query.offset(offset).limit(limit)

            result = await self.db.execute(query)
            items = result.scalars().all()
            # Build response (generic - works with any model)
            data = [output_schema.from_orm(item) for item in items]       
            # Create cursors for hybrid support
            next_cursor = None
            previous_cursor = None
            
            # if items:
            #     if page < total_pages:
            #         last_item = items[-1]
            #         next_cursor = encode_cursor(CursorData(
            #             id=last_item.id,
            #             created_at=getattr(last_item, 'created_at', datetime.utcnow()),
            #             sort_field=sort_by,
            #             sort_value=getattr(last_item, sort_by, None)
            #         ))
                
            #     if page > 1:
            #         first_item = items[0]
            #         previous_cursor = encode_cursor(CursorData(
            #             id=first_item.id,
            #             created_at=getattr(first_item, 'created_at', datetime.utcnow()),
            #             sort_field=sort_by,
            #             sort_value=getattr(first_item, sort_by, None)
            #         ))
            
            pagination = PaginationInfo(
                current_page=page,
                total_pages=total_pages,
                total_items=total_items,
                items_per_page=limit,
                has_next=page < total_pages,
                has_previous=page > 1,
                next_cursor=next_cursor,
                previous_cursor=previous_cursor
            )
            
            #links = self._build_offset_links(page, total_pages, limit, sort_by, sort_order)
            
            return PaginatedResponse(data=data, pagination=pagination, links=None)

    def _cursor_paginate(
            self, 
            query, 
            model_class,    
            output_schema,
            cursor: Optional[str], 
            limit: int, 
            sort_by: str, 
            sort_order: SortOrder
        ) -> PaginatedResponse:
            
            # Apply sorting
            sort_column = getattr(model_class, sort_by, getattr(model_class, "created_at", getattr(model_class, "id")))
            
            if cursor:
                cursor_data = decode_cursor(cursor)
                
                # Apply cursor conditions based on sort order
                if sort_order == SortOrder.desc:
                    if sort_by == "created_at":
                        created_at_col = getattr(model_class, "created_at")
                        id_col = getattr(model_class, "id")
                        query = query.filter(
                            or_(
                                created_at_col < cursor_data.created_at,
                                and_(
                                    created_at_col == cursor_data.created_at,
                                    id_col < cursor_data.id
                                )
                            )
                        )
                    else:
                        # For other fields, use composite sorting
                        sort_value = cursor_data.sort_value
                        id_col = getattr(model_class, "id")
                        query = query.filter(
                            or_(
                                sort_column < sort_value,
                                and_(
                                    sort_column == sort_value,
                                    id_col < cursor_data.id
                                )
                            )
                        )
                    query = query.order_by(desc(sort_column), desc(getattr(model_class, "id")))
                else:
                    if sort_by == "created_at":
                        created_at_col = getattr(model_class, "created_at")
                        id_col = getattr(model_class, "id")
                        query = query.filter(
                            or_(
                                created_at_col > cursor_data.created_at,
                                and_(
                                    created_at_col == cursor_data.created_at,
                                    id_col > cursor_data.id
                                )
                            )
                        )
                    else:
                        sort_value = cursor_data.sort_value
                        id_col = getattr(model_class, "id")
                        query = query.filter(
                            or_(
                                sort_column > sort_value,
                                and_(
                                    sort_column == sort_value,
                                    id_col > cursor_data.id
                                )
                            )
                        )
                    query = query.order_by(asc(sort_column), asc(getattr(model_class, "id")))
            else:
                # First page
                if sort_order == SortOrder.desc:
                    query = query.order_by(desc(sort_column), desc(getattr(model_class, "id")))
                else:
                    query = query.order_by(asc(sort_column), asc(getattr(model_class, "id")))
            
            # Fetch one extra item to determine if there's a next page
            items = query.limit(limit + 1).all()
            
            has_next = len(items) > limit
            if has_next:
                items = items[:limit]
            
            # Build response (generic - works with any model)
            data = [item.__dict__ for item in items]
            # Remove SQLAlchemy internal attributes
            for item_dict in data:
                item_dict.pop('_sa_instance_state', None)
            
            # Create cursors
            next_cursor = None
            previous_cursor = None
            
            if items:
                if has_next:
                    last_item = items[-1]
                    next_cursor = encode_cursor(CursorData(
                        id=last_item.id,
                        created_at=getattr(last_item, 'created_at', datetime.utcnow()),
                        sort_field=sort_by,
                        sort_value=getattr(last_item, sort_by, None)
                    ))
                
                # For previous cursor, we'd need to implement reverse pagination
                # This is a simplified version
                if cursor:
                    previous_cursor = "prev_" + cursor  # Simplified for demo
            
            pagination = PaginationInfo(
                items_per_page=limit,
                has_next=has_next,
                has_previous=cursor is not None,
                next_cursor=next_cursor,
                previous_cursor=previous_cursor
            )
            
            links = self._build_cursor_links(cursor, next_cursor, limit, sort_by, sort_order)
            
            return PaginatedResponse(data=data, pagination=pagination, links=links)
    
    def _build_offset_links(self, page: int, total_pages: int, limit: int, sort_by: str, sort_order: SortOrder) -> PaginationLinks:
        base_url = "/api/v1/products"
        query_params = f"limit={limit}&sort_by={sort_by}&sort_order={sort_order.value}"
        
        return PaginationLinks(
            first=f"{base_url}?page=1&{query_params}" if total_pages > 0 else None,
            previous=f"{base_url}?page={page-1}&{query_params}" if page > 1 else None,
            next=f"{base_url}?page={page+1}&{query_params}" if page < total_pages else None,
            last=f"{base_url}?page={total_pages}&{query_params}" if total_pages > 0 else None
        )
        
    def _build_cursor_links(self, cursor: Optional[str], next_cursor: Optional[str], limit: int, sort_by: str, sort_order: SortOrder) -> PaginationLinks:
        base_url = "/api/v1/products"
        query_params = f"limit={limit}&sort_by={sort_by}&sort_order={sort_order}"
        
        return PaginationLinks(
            next=f"{base_url}?cursor={next_cursor}&{query_params}" if next_cursor else None,
            previous=f"{base_url}?cursor={cursor}&{query_params}" if cursor else None
        )