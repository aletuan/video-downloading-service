#!/usr/bin/env python3
"""
Development Environment Setup Script

This script performs a complete development environment setup for the YouTube Video Download Service.
It handles environment cleanup, Docker setup, database initialization, and creates initial admin API keys.

Usage:
    python scripts/setup_dev.py [OPTIONS]

Options:
    --clean-all         Clean everything (containers, volumes, images)
    --clean-containers  Clean only containers and volumes (keep images)
    --no-clean          Skip cleanup (default)
    --no-build          Skip Docker build (use existing images)
    --admin-key-name    Name for admin API key (default: "Development Admin")
    --skip-key          Skip admin API key creation
    --help             Show this help message

Examples:
    # Basic setup (no cleanup)
    python scripts/setup_dev.py

    # Full reset and setup
    python scripts/setup_dev.py --clean-all

    # Clean containers only and setup
    python scripts/setup_dev.py --clean-containers

    # Setup without building (faster if images exist)
    python scripts/setup_dev.py --no-build
"""

import sys
import os
import subprocess
import asyncio
import argparse
import time
from pathlib import Path
from typing import Optional

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Colors for output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_header(message: str):
    """Print a formatted header message."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{message.center(80)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}")


def print_step(step: str, message: str):
    """Print a formatted step message."""
    print(f"\n{Colors.OKBLUE}{Colors.BOLD}[{step}]{Colors.ENDC} {message}")


def print_success(message: str):
    """Print a success message."""
    print(f"{Colors.OKGREEN}✅ {message}{Colors.ENDC}")


def print_warning(message: str):
    """Print a warning message."""
    print(f"{Colors.WARNING}⚠️  {message}{Colors.ENDC}")


def print_error(message: str):
    """Print an error message."""
    print(f"{Colors.FAIL}❌ {message}{Colors.ENDC}")


def run_command(command: str, description: str, check: bool = True, shell: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command with formatted output."""
    print(f"  🔧 {description}")
    print(f"     Command: {Colors.OKCYAN}{command}{Colors.ENDC}")
    
    try:
        result = subprocess.run(
            command,
            shell=shell,
            capture_output=True,
            text=True,
            check=check
        )
        
        if result.stdout:
            print(f"     Output: {result.stdout.strip()}")
        
        if result.returncode == 0:
            print_success(f"Completed: {description}")
        else:
            print_warning(f"Command completed with return code: {result.returncode}")
            if result.stderr:
                print(f"     Error: {result.stderr.strip()}")
        
        return result
        
    except subprocess.CalledProcessError as e:
        print_error(f"Failed: {description}")
        print(f"     Error: {e.stderr.strip() if e.stderr else 'Unknown error'}")
        if check:
            raise
        return e


def check_prerequisites():
    """Check if required tools are available."""
    print_step("PREREQ", "Checking prerequisites")
    
    required_tools = [
        ("docker", "Docker"),
        ("docker compose", "Docker Compose")
    ]
    
    missing_tools = []
    
    for command, tool_name in required_tools:
        try:
            result = subprocess.run(
                f"{command} --version",
                shell=True,
                capture_output=True,
                text=True,
                check=True
            )
            version = result.stdout.strip().split('\n')[0]
            print_success(f"{tool_name}: {version}")
        except subprocess.CalledProcessError:
            print_error(f"{tool_name} not found")
            missing_tools.append(tool_name)
    
    if missing_tools:
        print_error(f"Missing required tools: {', '.join(missing_tools)}")
        print("\n📋 Installation instructions:")
        print("• Docker: https://docs.docker.com/get-docker/")
        print("• Docker Compose: https://docs.docker.com/compose/install/")
        sys.exit(1)
    
    print_success("All prerequisites met")


def cleanup_environment(clean_level: str):
    """Clean up existing Docker environment."""
    if clean_level == "none":
        print_step("CLEANUP", "Skipping cleanup (--no-clean)")
        return
    
    print_step("CLEANUP", f"Cleaning up environment (level: {clean_level})")
    
    # Stop and remove containers
    print("  🛑 Stopping containers...")
    run_command("docker compose down", "Stop Docker Compose services", check=False)
    
    if clean_level in ["containers", "all"]:
        print("  🗑️  Removing containers and volumes...")
        run_command("docker compose down -v", "Remove containers and volumes", check=False)
        
        # Remove any orphaned containers
        run_command(
            "docker container prune -f", 
            "Remove orphaned containers", 
            check=False
        )
        
        # Remove volumes
        run_command(
            "docker volume prune -f",
            "Remove unused volumes",
            check=False
        )
    
    if clean_level == "all":
        print("  🗑️  Removing images...")
        run_command(
            "docker image prune -af",
            "Remove unused images",
            check=False
        )
        
        # Remove project-specific images
        project_images = [
            "video-downloading-service-app",
            "video-downloading-service-celery-worker"
        ]
        
        for image in project_images:
            run_command(
                f"docker image rm {image}",
                f"Remove {image} image",
                check=False
            )
    
    print_success("Environment cleanup completed")


def build_and_start_services(no_build: bool = False):
    """Build and start Docker services."""
    print_step("DOCKER", "Setting up Docker services")
    
    if no_build:
        print("  🚀 Starting services without building...")
        run_command(
            "docker compose up -d",
            "Start services"
        )
    else:
        print("  🔨 Building and starting services...")
        run_command(
            "docker compose up -d --build",
            "Build and start services"
        )
    
    # Wait for services to be ready
    print("  ⏳ Waiting for services to be ready...")
    max_attempts = 30
    attempt = 0
    
    while attempt < max_attempts:
        try:
            result = subprocess.run(
                "curl -s http://localhost:8000/health",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0 and "healthy" in result.stdout:
                print_success("Services are ready!")
                break
                
        except subprocess.TimeoutExpired:
            pass
        
        attempt += 1
        print(f"     Attempt {attempt}/{max_attempts}...")
        time.sleep(2)
    
    if attempt >= max_attempts:
        print_error("Services failed to start within timeout")
        print("🔧 Try checking the logs:")
        print("   docker compose logs app")
        print("   docker compose logs db")
        print("   docker compose logs redis")
        sys.exit(1)


def run_database_migrations():
    """Run database migrations."""
    print_step("DATABASE", "Running database migrations")
    
    # Wait a bit more for database to be fully ready
    time.sleep(3)
    
    # Run migrations
    run_command(
        "docker compose exec -T app alembic upgrade head",
        "Run Alembic migrations"
    )
    
    print_success("Database migrations completed")


def verify_services():
    """Verify that all services are running correctly."""
    print_step("VERIFY", "Verifying services")
    
    services_to_check = [
        ("http://localhost:8000/health", "FastAPI App"),
        ("http://localhost:8000/health/detailed", "Detailed Health Check")
    ]
    
    for url, service_name in services_to_check:
        try:
            result = subprocess.run(
                f"curl -s {url}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                print_success(f"{service_name}: OK")
                if "detailed" in url:
                    # Pretty print the detailed health check
                    run_command(
                        f"curl -s {url} | python -m json.tool",
                        "Detailed health check output",
                        check=False
                    )
            else:
                print_error(f"{service_name}: Failed")
                
        except subprocess.TimeoutExpired:
            print_error(f"{service_name}: Timeout")


async def create_admin_key(admin_key_name: str) -> Optional[str]:
    """Create admin API key using the create_admin_key script."""
    print_step("API-KEY", "Creating admin API key")
    
    try:
        # Import here to avoid import issues
        from app.core.auth import APIKeyGenerator
        from app.models.database import APIKey
        from app.core.database import get_db_session, init_database
        from datetime import datetime, timezone
        
        # Initialize database
        await init_database()
        
        # Generate API key
        api_key = APIKeyGenerator.generate_api_key()
        api_key_hash = APIKeyGenerator.hash_api_key(api_key)
        
        # Create database record
        async with get_db_session() as session:
            admin_key = APIKey(
                name=admin_key_name,
                key_hash=api_key_hash,
                permission_level='admin',
                is_active=True,
                description=f"Development admin key created by setup_dev.py on {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
                usage_count=0,
                created_by='setup_dev_script',
                created_at=datetime.now(timezone.utc)
            )
            session.add(admin_key)
            await session.commit()
            await session.refresh(admin_key)
            
            print_success(f"Admin API key created: {admin_key_name}")
            print(f"  🔑 Key: {Colors.BOLD}{api_key}{Colors.ENDC}")
            print(f"  🆔 ID: {admin_key.id}")
            
            return api_key
            
    except Exception as e:
        print_error(f"Failed to create admin API key: {e}")
        return None


def create_development_files():
    """Create useful development files."""
    print_step("FILES", "Creating development files")
    
    # Create .env.local if it doesn't exist
    env_local_path = Path(".env.local")
    if not env_local_path.exists():
        env_content = """# Local development overrides
# Copy this to .env.local and customize as needed

# Debug mode
DEBUG=true

# Database (Docker defaults)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/youtube_service

# Redis (Docker defaults)
REDIS_URL=redis://localhost:6380/0

# Local storage
DOWNLOAD_BASE_PATH=./downloads
ENVIRONMENT=localhost

# Host and port
HOST=0.0.0.0
PORT=8000
"""
        with open(env_local_path, 'w') as f:
            f.write(env_content)
        print_success("Created .env.local template")
    else:
        print_success(".env.local already exists")


def print_setup_summary(admin_key: Optional[str]):
    """Print a summary of the setup."""
    print_header("🎉 DEVELOPMENT ENVIRONMENT SETUP COMPLETE!")
    
    print(f"\n{Colors.OKGREEN}✅ Services Running:{Colors.ENDC}")
    print("  • FastAPI App: http://localhost:8000")
    print("  • API Documentation: http://localhost:8000/docs")
    print("  • Database: PostgreSQL on localhost:5433")
    print("  • Redis: Redis on localhost:6380")
    print("  • File Downloads: ./downloads/")
    
    if admin_key:
        print(f"\n{Colors.OKGREEN}🔑 Admin API Key:{Colors.ENDC}")
        print(f"  {Colors.BOLD}{admin_key}{Colors.ENDC}")
        
        print(f"\n{Colors.OKGREEN}🧪 Quick Tests:{Colors.ENDC}")
        print("  # Test health endpoint")
        print("  curl http://localhost:8000/health")
        print("\n  # Test admin API")
        print(f'  curl -H "X-API-Key: {admin_key}" http://localhost:8000/api/v1/admin/api-keys')
        print("\n  # Create a download key")
        print(f"""  curl -X POST "http://localhost:8000/api/v1/admin/api-keys" \\
       -H "Content-Type: application/json" \\
       -H "X-API-Key: {admin_key}" \\
       -d '{{"name": "My Download Key", "permission_level": "download"}}'""")
    
    print(f"\n{Colors.OKGREEN}🛠️  Development Commands:{Colors.ENDC}")
    print("  # View logs")
    print("  docker compose logs -f")
    print("\n  # Access app container")
    print("  docker compose exec app bash")
    print("\n  # Run migrations")
    print("  docker compose exec app alembic upgrade head")
    print("\n  # Stop services")
    print("  docker compose down")
    print("\n  # Reset everything")
    print("  python scripts/setup_dev.py --clean-all")
    
    print(f"\n{Colors.WARNING}📁 Project Structure:{Colors.ENDC}")
    print("  • app/ - Main application code")
    print("  • tests/ - Test suites")
    print("  • scripts/ - Utility scripts")
    print("  • docs/ - Documentation")
    print("  • downloads/ - Downloaded files (local)")
    
    print(f"\n{Colors.HEADER}🚀 Happy coding!{Colors.ENDC}")


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Setup development environment for YouTube Video Download Service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/setup_dev.py                    # Basic setup
  python scripts/setup_dev.py --clean-all        # Full reset and setup
  python scripts/setup_dev.py --clean-containers # Clean containers only
  python scripts/setup_dev.py --no-build         # Skip Docker build
        """
    )
    
    cleanup_group = parser.add_mutually_exclusive_group()
    cleanup_group.add_argument(
        '--clean-all',
        action='store_true',
        help='Clean everything (containers, volumes, images) before setup'
    )
    cleanup_group.add_argument(
        '--clean-containers',
        action='store_true',
        help='Clean containers and volumes only (keep images)'
    )
    cleanup_group.add_argument(
        '--no-clean',
        action='store_true',
        help='Skip cleanup (default behavior)'
    )
    
    parser.add_argument(
        '--no-build',
        action='store_true',
        help='Skip Docker build (use existing images)'
    )
    
    parser.add_argument(
        '--admin-key-name',
        default='Development Admin',
        help='Name for the admin API key (default: "Development Admin")'
    )
    
    parser.add_argument(
        '--skip-key',
        action='store_true',
        help='Skip admin API key creation'
    )
    
    return parser.parse_args()


async def main():
    """Main function."""
    args = parse_arguments()
    
    print_header("🚀 YOUTUBE VIDEO DOWNLOAD SERVICE - DEV SETUP")
    
    # Determine cleanup level
    if args.clean_all:
        clean_level = "all"
    elif args.clean_containers:
        clean_level = "containers"
    else:
        clean_level = "none"
    
    admin_key = None
    
    try:
        # Step 1: Check prerequisites
        check_prerequisites()
        
        # Step 2: Cleanup environment
        cleanup_environment(clean_level)
        
        # Step 3: Build and start services
        build_and_start_services(args.no_build)
        
        # Step 4: Run database migrations
        run_database_migrations()
        
        # Step 5: Verify services
        verify_services()
        
        # Step 6: Create development files
        create_development_files()
        
        # Step 7: Create admin API key
        if not args.skip_key:
            admin_key = await create_admin_key(args.admin_key_name)
        
        # Step 8: Print summary
        print_setup_summary(admin_key)
        
    except KeyboardInterrupt:
        print_error("\n\nSetup interrupted by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"\nSetup failed: {e}")
        print("\n🔧 Troubleshooting:")
        print("• Check Docker is running: docker --version")
        print("• View logs: docker compose logs")
        print("• Clean and retry: python scripts/setup_dev.py --clean-all")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Setup cancelled by user")
        sys.exit(0)