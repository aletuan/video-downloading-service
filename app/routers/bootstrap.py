"""
Bootstrap API endpoints for YouTube Video Download Service.

This module provides a one-time setup endpoint for creating the initial admin API key
without requiring existing authentication. This solves the "chicken and egg" problem
for production deployments.

Security Features:
- Only works when no admin keys exist in the database
- Requires BOOTSTRAP_SETUP_TOKEN from environment variables
- Automatically disables itself after creating the first admin key
- Comprehensive audit logging for all attempts
"""

import hashlib
import secrets
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field, field_validator

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.validation import InputValidator
from app.models.database import APIKey

logger = logging.getLogger(__name__)

router = APIRouter()


# Pydantic models for bootstrap endpoints

class BootstrapAdminKeyRequest(BaseModel):
    """Request model for creating a bootstrap admin key."""
    name: str = Field(..., min_length=1, max_length=100, description="Human-readable name for the admin API key")
    description: Optional[str] = Field(None, max_length=500, description="Optional description for the admin key")
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        """Validate API key name using security validator."""
        return InputValidator.validate_api_key_name(v)
    
    @field_validator('description')
    @classmethod
    def validate_description(cls, v):
        """Validate description if provided."""
        if v is not None:
            return InputValidator.validate_description(v, max_length=500)
        return v


class BootstrapAdminKeyResponse(BaseModel):
    """Response model for successful bootstrap admin key creation."""
    api_key: str = Field(..., description="The generated admin API key (one-time display)")
    key_id: str = Field(..., description="UUID of the created API key")
    name: str = Field(..., description="Name of the created API key")
    permission_level: str = Field(..., description="Permission level (admin)")
    message: str = Field(..., description="Success message")
    next_steps: str = Field(..., description="Instructions for next steps")


# Helper functions

async def check_existing_admin_keys(db: AsyncSession) -> bool:
    """
    Check if any admin or full_access API keys exist in the database.
    
    Returns:
        True if admin keys exist, False if no admin keys exist
    """
    try:
        result = await db.execute(
            select(func.count(APIKey.id))
            .where(APIKey.permission_level.in_(['admin', 'full_access']))
            .where(APIKey.is_active == True)
        )
        count = result.scalar()
        
        logger.info(f"Bootstrap check: Found {count} existing admin keys")
        return count > 0
        
    except Exception as e:
        logger.error(f"Error checking existing admin keys: {e}")
        raise HTTPException(status_code=500, detail="Database error during bootstrap check")


async def create_bootstrap_admin_key(
    db: AsyncSession, 
    name: str, 
    description: Optional[str] = None
) -> tuple[APIKey, str]:
    """
    Create a new admin API key for bootstrap purposes.
    
    Returns:
        Tuple of (APIKey object, raw API key string)
    """
    try:
        # Generate secure API key
        api_key = f"yvs_{secrets.token_urlsafe(48)}"
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        # Create API key object
        new_key = APIKey(
            name=name,
            key_hash=key_hash,
            permission_level='admin',
            description=description or "Bootstrap admin key created via setup endpoint",
            is_active=True,
            created_by='bootstrap_endpoint',
            usage_count=0
        )
        
        db.add(new_key)
        await db.commit()
        await db.refresh(new_key)
        
        logger.info(f"Bootstrap admin key created: {new_key.id} - {name}")
        return new_key, api_key
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating bootstrap admin key: {e}")
        raise HTTPException(status_code=500, detail="Failed to create bootstrap admin key")


# Bootstrap endpoints

@router.post("/bootstrap/admin-key", response_model=BootstrapAdminKeyResponse)
async def bootstrap_admin_key(
    request: BootstrapAdminKeyRequest,
    x_setup_token: str = Header(..., alias="X-Setup-Token"),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
):
    """
    Create the initial admin API key for system bootstrap.
    
    This endpoint:
    - Only works when no admin keys exist in the database
    - Requires a valid setup token from environment variables
    - Automatically disables itself after creating the first admin key
    - Logs all attempts for security auditing
    
    **Security Note**: This endpoint becomes inaccessible after the first admin key is created.
    """
    
    # Log the bootstrap attempt
    logger.warning(f"Bootstrap admin key attempt: name='{request.name}', has_token={bool(x_setup_token)}")
    
    try:
        # 1. Check if any admin keys already exist
        admin_keys_exist = await check_existing_admin_keys(db)
        if admin_keys_exist:
            logger.warning("Bootstrap attempt rejected: Admin keys already exist")
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Bootstrap disabled",
                    "message": "Admin API keys already exist in the system. Bootstrap endpoint is automatically disabled.",
                    "suggestion": "Use existing admin credentials or contact system administrator."
                }
            )
        
        # 2. Validate setup token
        if not x_setup_token or x_setup_token.strip() != settings.bootstrap_setup_token.strip():
            logger.warning(f"Bootstrap attempt with invalid token")
            raise HTTPException(
                status_code=401,
                detail={
                    "error": "Invalid setup token",
                    "message": "The provided setup token is invalid or missing.",
                    "header_required": "X-Setup-Token"
                }
            )
        
        # 3. Create the bootstrap admin key
        api_key_obj, raw_api_key = await create_bootstrap_admin_key(
            db=db,
            name=request.name,
            description=request.description
        )
        
        # 4. Log successful bootstrap
        logger.warning(f"SUCCESS: Bootstrap admin key created - ID: {api_key_obj.id}, Name: '{request.name}'")
        
        # 5. Return the response
        return BootstrapAdminKeyResponse(
            api_key=raw_api_key,
            key_id=str(api_key_obj.id),
            name=api_key_obj.name,
            permission_level=api_key_obj.permission_level,
            message="Bootstrap admin key created successfully! This endpoint is now disabled.",
            next_steps="Use this API key to create additional keys via /api/v1/admin/api-keys endpoints. Store the key securely - it cannot be retrieved again."
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions (they're already logged above)
        raise
    except Exception as e:
        logger.error(f"Unexpected error during bootstrap: {e}")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred during bootstrap setup"
        )


@router.get("/bootstrap/status")
async def bootstrap_status(
    db: AsyncSession = Depends(get_db)
):
    """
    Check if bootstrap is available or if admin keys already exist.
    
    This endpoint helps determine if the system needs initial setup.
    """
    try:
        admin_keys_exist = await check_existing_admin_keys(db)
        
        if admin_keys_exist:
            return {
                "bootstrap_available": False,
                "message": "System is already set up with admin keys",
                "status": "configured"
            }
        else:
            return {
                "bootstrap_available": True,
                "message": "System requires bootstrap setup",
                "status": "needs_setup",
                "endpoint": "POST /api/v1/bootstrap/admin-key",
                "required_header": "X-Setup-Token"
            }
            
    except Exception as e:
        logger.error(f"Error checking bootstrap status: {e}")
        raise HTTPException(status_code=500, detail="Error checking system status")