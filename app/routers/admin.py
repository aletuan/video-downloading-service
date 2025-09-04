"""
Admin API endpoints for YouTube Video Download Service.

This module provides administrative endpoints for:
- API key management (create, list, update, delete)
- System monitoring and statistics
- User management
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import uuid
import logging

from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, update as sqlalchemy_update, delete
from pydantic import BaseModel, Field, validator

from app.core.validation import InputValidator

from app.core.database import get_db
from app.core.auth import (
    require_admin_permission,
    APIKeyGenerator,
    APIKeyPermission
)
from app.models.database import APIKey, DownloadJob

logger = logging.getLogger(__name__)

router = APIRouter()


# Pydantic models for admin endpoints

class APIKeyCreateRequest(BaseModel):
    """Request model for creating a new API key."""
    name: str = Field(..., min_length=1, max_length=100, description="Human-readable name for the API key")
    
    @validator('name')
    def validate_name(cls, v):
        """Validate API key name using security validator."""
        return InputValidator.validate_api_key_name(v)
    permission_level: APIKeyPermission = Field(default=APIKeyPermission.READ_ONLY, description="Permission level")
    description: Optional[str] = Field(None, max_length=500, description="Optional description")
    
    @validator('description')
    def validate_description(cls, v):
        """Validate description using security validator."""
        if v is None:
            return v
        return InputValidator.validate_description(v, max_length=500)
    expires_at: Optional[datetime] = Field(None, description="Optional expiration date")
    custom_rate_limit: Optional[int] = Field(None, ge=1, le=10000, description="Custom rate limit per minute")
    notes: Optional[str] = Field(None, max_length=1000, description="Additional notes")
    
    @validator('notes')
    def validate_notes(cls, v):
        """Validate notes using security validator."""
        if v is None:
            return v
        return InputValidator.validate_description(v, max_length=1000)


class APIKeyResponse(BaseModel):
    """Response model for API key operations."""
    id: str
    name: str
    permission_level: str
    is_active: bool
    description: Optional[str]
    usage_count: int
    custom_rate_limit: Optional[int]
    created_at: datetime
    updated_at: Optional[datetime]
    expires_at: Optional[datetime]
    created_by: Optional[str]
    notes: Optional[str]
    is_expired: bool
    is_valid: bool
    days_until_expiry: Optional[int]


class APIKeyCreateResponse(BaseModel):
    """Response model for API key creation (includes the actual key)."""
    api_key: str = Field(..., description="The generated API key (only shown once)")
    key_info: APIKeyResponse = Field(..., description="API key metadata")


class APIKeyListResponse(BaseModel):
    """Response model for API key listing."""
    api_keys: List[APIKeyResponse]
    total: int
    page: int
    per_page: int
    pages: int


class APIKeyUpdateRequest(BaseModel):
    """Request model for updating an API key."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    permission_level: Optional[APIKeyPermission] = None
    is_active: Optional[bool] = None
    description: Optional[str] = Field(None, max_length=500)
    expires_at: Optional[datetime] = None
    custom_rate_limit: Optional[int] = Field(None, ge=1, le=10000)
    notes: Optional[str] = Field(None, max_length=1000)
    
    @validator('name')
    def validate_name(cls, v):
        """Validate API key name using security validator."""
        if v is None:
            return v
        return InputValidator.validate_api_key_name(v)
    
    @validator('description')
    def validate_description(cls, v):
        """Validate description using security validator."""
        if v is None:
            return v
        return InputValidator.validate_description(v, max_length=500)
    
    @validator('notes')
    def validate_notes(cls, v):
        """Validate notes using security validator."""
        if v is None:
            return v
        return InputValidator.validate_description(v, max_length=1000)


class SystemStatsResponse(BaseModel):
    """Response model for system statistics."""
    total_api_keys: int
    active_api_keys: int
    total_downloads: int
    successful_downloads: int
    failed_downloads: int
    downloads_last_24h: int
    downloads_last_7d: int
    top_users: List[Dict[str, Any]]


# Admin endpoints

@router.post(
    "/api-keys",
    response_model=APIKeyCreateResponse,
    summary="Create new API key",
    description="Generate a new API key with specified permissions"
)
async def create_api_key(
    request: APIKeyCreateRequest,
    db: AsyncSession = Depends(get_db),
    admin_info: dict = Depends(require_admin_permission)
):
    """
    Create a new API key.
    
    This endpoint generates a new API key with the specified permissions
    and stores it securely in the database.
    """
    try:
        # Generate new API key
        api_key = APIKeyGenerator.generate_api_key()
        api_key_hash = APIKeyGenerator.hash_api_key(api_key)
        
        # Create API key record
        api_key_record = APIKey(
            name=request.name,
            key_hash=api_key_hash,
            permission_level=request.permission_level,
            description=request.description,
            expires_at=request.expires_at,
            custom_rate_limit=request.custom_rate_limit,
            created_by=admin_info["name"],
            notes=request.notes
        )
        
        db.add(api_key_record)
        await db.commit()
        await db.refresh(api_key_record)
        
        logger.info(f"API key created: {request.name} by {admin_info['name']}")
        
        return APIKeyCreateResponse(
            api_key=api_key,
            key_info=APIKeyResponse(**api_key_record.to_dict())
        )
        
    except Exception as e:
        logger.error(f"Failed to create API key: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create API key: {str(e)}"
        )


@router.get(
    "/api-keys",
    response_model=APIKeyListResponse,
    summary="List API keys",
    description="Get a paginated list of API keys"
)
async def list_api_keys(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(10, ge=1, le=100, description="Keys per page"),
    active_only: bool = Query(False, description="Show only active keys"),
    permission_level: Optional[APIKeyPermission] = Query(None, description="Filter by permission level"),
    db: AsyncSession = Depends(get_db),
    admin_info: dict = Depends(require_admin_permission)
):
    """
    List API keys with pagination and filtering.
    
    Returns a paginated list of API keys with optional filtering
    by active status and permission level.
    """
    try:
        # Build query
        query = select(APIKey)
        
        # Apply filters
        if active_only:
            query = query.where(APIKey.is_active == True)
        
        if permission_level:
            query = query.where(APIKey.permission_level == permission_level)
        
        # Get total count
        count_query = select(func.count(APIKey.id))
        if active_only:
            count_query = count_query.where(APIKey.is_active == True)
        if permission_level:
            count_query = count_query.where(APIKey.permission_level == permission_level)
        
        total_result = await db.execute(count_query)
        total = total_result.scalar()
        
        # Apply pagination
        query = query.order_by(desc(APIKey.created_at))
        query = query.offset((page - 1) * per_page).limit(per_page)
        
        # Execute query
        result = await db.execute(query)
        api_keys = result.scalars().all()
        
        # Calculate pagination info
        pages = (total + per_page - 1) // per_page
        
        return APIKeyListResponse(
            api_keys=[APIKeyResponse(**key.to_dict()) for key in api_keys],
            total=total,
            page=page,
            per_page=per_page,
            pages=pages
        )
        
    except Exception as e:
        logger.error(f"Failed to list API keys: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list API keys: {str(e)}"
        )


@router.get(
    "/api-keys/{key_id}",
    response_model=APIKeyResponse,
    summary="Get API key details",
    description="Get detailed information about a specific API key"
)
async def get_api_key(
    key_id: str,
    db: AsyncSession = Depends(get_db),
    admin_info: dict = Depends(require_admin_permission)
):
    """
    Get detailed information about a specific API key.
    """
    try:
        # Find API key
        result = await db.execute(
            select(APIKey).where(APIKey.id == key_id)
        )
        api_key = result.scalar_one_or_none()
        
        if not api_key:
            raise HTTPException(
                status_code=404,
                detail="API key not found"
            )
        
        return APIKeyResponse(**api_key.to_dict())
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get API key {key_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get API key: {str(e)}"
        )


@router.put(
    "/api-keys/{key_id}",
    response_model=APIKeyResponse,
    summary="Update API key",
    description="Update API key properties"
)
async def update_api_key(
    key_id: str,
    request: APIKeyUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin_info: dict = Depends(require_admin_permission)
):
    """
    Update API key properties.
    
    Allows updating name, permissions, active status, expiration, etc.
    """
    try:
        # Find API key
        result = await db.execute(
            select(APIKey).where(APIKey.id == key_id)
        )
        api_key = result.scalar_one_or_none()
        
        if not api_key:
            raise HTTPException(
                status_code=404,
                detail="API key not found"
            )
        
        # Update fields
        update_data = {}
        for field, value in request.dict(exclude_unset=True).items():
            if hasattr(api_key, field):
                update_data[field] = value
        
        if update_data:
            update_data['updated_at'] = datetime.utcnow()
            
            await db.execute(
                sqlalchemy_update(APIKey)
                .where(APIKey.id == key_id)
                .values(**update_data)
            )
            await db.commit()
            await db.refresh(api_key)
            
            logger.info(f"API key updated: {api_key.name} by {admin_info['name']}")
        
        return APIKeyResponse(**api_key.to_dict())
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update API key {key_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update API key: {str(e)}"
        )


@router.delete(
    "/api-keys/{key_id}",
    summary="Delete API key",
    description="Permanently delete an API key"
)
async def delete_api_key(
    key_id: str,
    db: AsyncSession = Depends(get_db),
    admin_info: dict = Depends(require_admin_permission)
):
    """
    Delete an API key permanently.
    
    This action cannot be undone.
    """
    try:
        # Find API key first
        result = await db.execute(
            select(APIKey).where(APIKey.id == key_id)
        )
        api_key = result.scalar_one_or_none()
        
        if not api_key:
            raise HTTPException(
                status_code=404,
                detail="API key not found"
            )
        
        # Delete API key
        await db.execute(
            delete(APIKey).where(APIKey.id == key_id)
        )
        await db.commit()
        
        logger.info(f"API key deleted: {api_key.name} by {admin_info['name']}")
        
        return {"message": f"API key '{api_key.name}' deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete API key {key_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete API key: {str(e)}"
        )


@router.get(
    "/stats",
    response_model=SystemStatsResponse,
    summary="Get system statistics",
    description="Get overall system usage statistics"
)
async def get_system_stats(
    db: AsyncSession = Depends(get_db),
    admin_info: dict = Depends(require_admin_permission)
):
    """
    Get system-wide statistics.
    
    Returns statistics about API keys, downloads, and usage patterns.
    """
    try:
        # Get API key statistics
        api_key_stats = await db.execute(
            select(
                func.count(APIKey.id).label('total'),
                func.sum(func.cast(APIKey.is_active, db.bind.dialect.name == 'postgresql' and 'integer' or 'int')).label('active')
            )
        )
        api_stats = api_key_stats.first()
        
        # Get download statistics
        download_stats = await db.execute(
            select(
                func.count(DownloadJob.id).label('total'),
                func.sum(func.case([(DownloadJob.status == 'completed', 1)], else_=0)).label('successful'),
                func.sum(func.case([(DownloadJob.status == 'failed', 1)], else_=0)).label('failed')
            )
        )
        dl_stats = download_stats.first()
        
        # Get recent download statistics
        now = datetime.utcnow()
        last_24h = now - timedelta(hours=24)
        last_7d = now - timedelta(days=7)
        
        downloads_24h = await db.execute(
            select(func.count(DownloadJob.id))
            .where(DownloadJob.created_at >= last_24h)
        )
        
        downloads_7d = await db.execute(
            select(func.count(DownloadJob.id))
            .where(DownloadJob.created_at >= last_7d)
        )
        
        # Get top API keys by usage
        top_users_result = await db.execute(
            select(APIKey.name, APIKey.usage_count, APIKey.permission_level)
            .order_by(desc(APIKey.usage_count))
            .limit(10)
        )
        
        top_users = [
            {
                "name": row.name,
                "usage_count": row.usage_count,
                "permission_level": row.permission_level
            }
            for row in top_users_result
        ]
        
        return SystemStatsResponse(
            total_api_keys=api_stats.total or 0,
            active_api_keys=api_stats.active or 0,
            total_downloads=dl_stats.total or 0,
            successful_downloads=dl_stats.successful or 0,
            failed_downloads=dl_stats.failed or 0,
            downloads_last_24h=downloads_24h.scalar() or 0,
            downloads_last_7d=downloads_7d.scalar() or 0,
            top_users=top_users
        )
        
    except Exception as e:
        logger.error(f"Failed to get system stats: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get system statistics: {str(e)}"
        )


# Export the router
__all__ = ["router"]