#!/usr/bin/env python3
"""
Create Admin API Key Script

This script creates an initial admin API key for the YouTube Video Download Service.
The admin key can then be used to create other API keys via the admin endpoints.

Usage:
    python scripts/create_admin_key.py [OPTIONS]

Options:
    --name NAME         Name for the admin key (default: "Initial Admin Key")
    --description DESC  Description for the admin key
    --expires DAYS      Number of days until expiration (default: no expiration)
    --docker            Run in Docker environment (uses Docker database connection)
    --help             Show this help message

Examples:
    # Create basic admin key
    python scripts/create_admin_key.py

    # Create admin key with custom name and description
    python scripts/create_admin_key.py --name "Production Admin" --description "Main admin key for production"

    # Create admin key that expires in 365 days
    python scripts/create_admin_key.py --expires 365

    # Run in Docker environment
    python scripts/create_admin_key.py --docker
"""

import sys
import os
import argparse
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from app.core.auth import APIKeyGenerator
    from app.models.database import APIKey
    from app.core.database import get_db_session, init_database
    from app.core.config import settings
except ImportError as e:
    print(f"❌ Error importing application modules: {e}")
    print("💡 Make sure you're running this script from the project root directory")
    print("💡 Try: python scripts/create_admin_key.py")
    sys.exit(1)


async def create_admin_key(name: str, description: str = None, expires_days: int = None) -> tuple[str, str]:
    """
    Create an admin API key in the database.
    
    Args:
        name: Name for the API key
        description: Optional description
        expires_days: Number of days until expiration (None for no expiration)
        
    Returns:
        Tuple of (api_key, key_id)
    """
    try:
        # Initialize database connection
        await init_database()
        
        # Generate API key
        api_key = APIKeyGenerator.generate_api_key()
        api_key_hash = APIKeyGenerator.hash_api_key(api_key)
        
        # Calculate expiration date if specified
        expires_at = None
        if expires_days:
            expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)
        
        # Create database record
        async with get_db_session() as session:
            admin_key = APIKey(
                name=name,
                key_hash=api_key_hash,
                permission_level='admin',
                is_active=True,
                description=description or f"Admin API key created on {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
                usage_count=0,
                created_by='create_admin_key_script',
                created_at=datetime.now(timezone.utc),
                expires_at=expires_at
            )
            session.add(admin_key)
            await session.commit()
            await session.refresh(admin_key)
            
            return api_key, str(admin_key.id)
            
    except Exception as e:
        print(f"❌ Error creating admin key: {e}")
        raise


async def check_existing_admin_keys() -> list[dict]:
    """Check for existing admin keys in the database."""
    try:
        await init_database()
        
        from sqlalchemy import select
        async with get_db_session() as session:
            result = await session.execute(
                select(APIKey).where(
                    APIKey.permission_level.in_(['admin', 'full_access']),
                    APIKey.is_active == True
                )
            )
            admin_keys = result.scalars().all()
            
            return [
                {
                    'id': str(key.id),
                    'name': key.name,
                    'permission_level': key.permission_level,
                    'created_at': key.created_at,
                    'expires_at': key.expires_at,
                    'is_expired': key.is_expired
                }
                for key in admin_keys
            ]
            
    except Exception as e:
        print(f"⚠️  Warning: Could not check existing admin keys: {e}")
        return []


def print_success_message(api_key: str, key_id: str, name: str, expires_days: int = None):
    """Print a formatted success message with the API key details."""
    print("\n" + "="*80)
    print("🎉 ADMIN API KEY CREATED SUCCESSFULLY!")
    print("="*80)
    print(f"📋 Key Name: {name}")
    print(f"🔑 API Key ID: {key_id}")
    print(f"🔐 API Key: {api_key}")
    print(f"👑 Permission Level: admin")
    
    if expires_days:
        expiry_date = datetime.now(timezone.utc) + timedelta(days=expires_days)
        print(f"⏰ Expires: {expiry_date.strftime('%Y-%m-%d %H:%M:%S')} UTC ({expires_days} days)")
    else:
        print("⏰ Expires: Never")
    
    print("\n📝 USAGE INSTRUCTIONS:")
    print("="*40)
    print("1. Use this key in API requests:")
    print(f'   curl -H "X-API-Key: {api_key}" http://localhost:8000/api/v1/admin/api-keys')
    print("\n2. Create additional API keys via admin endpoints:")
    print(f'''   curl -X POST "http://localhost:8000/api/v1/admin/api-keys" \\
        -H "Content-Type: application/json" \\
        -H "X-API-Key: {api_key}" \\
        -d '{{"name": "My App Key", "permission_level": "download"}}' ''')
    
    print("\n3. Test authentication:")
    print(f'   curl -H "X-API-Key: {api_key}" http://localhost:8000/api/v1/jobs')
    
    print("\n⚠️  SECURITY NOTES:")
    print("="*20)
    print("• Store this API key securely - it cannot be retrieved again")
    print("• This key has admin permissions - handle with care")
    print("• Use environment variables or secure vaults in production")
    print("• Consider creating separate keys for different applications")
    print("="*80)


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Create an admin API key for the YouTube Video Download Service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/create_admin_key.py
  python scripts/create_admin_key.py --name "Production Admin" 
  python scripts/create_admin_key.py --expires 365 --docker
        """
    )
    
    parser.add_argument(
        '--name', 
        default='Initial Admin Key',
        help='Name for the admin API key (default: "Initial Admin Key")'
    )
    
    parser.add_argument(
        '--description',
        help='Description for the admin API key'
    )
    
    parser.add_argument(
        '--expires',
        type=int,
        metavar='DAYS',
        help='Number of days until the key expires (default: never expires)'
    )
    
    parser.add_argument(
        '--docker',
        action='store_true',
        help='Run in Docker environment (uses Docker database connection)'
    )
    
    parser.add_argument(
        '--force',
        action='store_true',
        help='Skip confirmation prompts (useful for automation)'
    )
    
    return parser.parse_args()


async def main():
    """Main function."""
    args = parse_arguments()
    
    print("🔑 YouTube Video Download Service - Admin Key Creator")
    print("=" * 60)
    
    # Check environment
    if args.docker:
        print("🐳 Running in Docker environment")
        os.environ['DATABASE_URL'] = 'postgresql+asyncpg://postgres:postgres@db:5432/youtube_service'
        os.environ['REDIS_URL'] = 'redis://redis:6379/0'
    else:
        print(f"🏠 Running in local environment")
        print(f"📊 Database: {settings.database_url.split('@')[-1] if '@' in settings.database_url else settings.database_url}")
    
    # Check for existing admin keys
    print("\n🔍 Checking for existing admin keys...")
    existing_keys = await check_existing_admin_keys()
    
    if existing_keys:
        print(f"⚠️  Found {len(existing_keys)} existing admin/full_access keys:")
        for key in existing_keys:
            status = "EXPIRED" if key['is_expired'] else "ACTIVE"
            expires = key['expires_at'].strftime('%Y-%m-%d') if key['expires_at'] else "Never"
            print(f"   • {key['name']} ({key['permission_level']}) - {status} - Expires: {expires}")
        
        if not args.force:
            response = input("\n❓ Continue creating another admin key? [y/N]: ")
            if response.lower() not in ['y', 'yes']:
                print("👋 Cancelled by user")
                return
    
    # Create the admin key
    try:
        print(f"\n🔨 Creating admin API key...")
        print(f"📋 Name: {args.name}")
        if args.description:
            print(f"📝 Description: {args.description}")
        if args.expires:
            print(f"⏰ Expires in: {args.expires} days")
        
        api_key, key_id = await create_admin_key(
            name=args.name,
            description=args.description,
            expires_days=args.expires
        )
        
        print_success_message(api_key, key_id, args.name, args.expires)
        
    except Exception as e:
        print(f"\n❌ Failed to create admin key: {e}")
        print("\n🔧 Troubleshooting tips:")
        print("• Make sure the database is running (docker compose up -d)")
        print("• Check that database migrations are up to date (alembic upgrade head)")
        print("• Verify environment variables are set correctly")
        print("• Try running with --docker flag if using Docker")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)