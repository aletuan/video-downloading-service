import sys
import os
import urllib.parse
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Add the project root to the path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import our models and configuration
from app.models.database import Base
from app.core.config import settings

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Set the database URL from our settings (convert async URL to sync for Alembic)
database_url = settings.database_url
if "sqlite+aiosqlite" in database_url:
    # Convert async SQLite URL to sync for Alembic
    database_url = database_url.replace("sqlite+aiosqlite", "sqlite")
elif "postgresql+asyncpg" in database_url:
    # Convert async PostgreSQL URL to sync for Alembic  
    database_url = database_url.replace("postgresql+asyncpg", "postgresql")

# Convert SSL parameter for psycopg2 compatibility
# asyncpg uses 'ssl=require' but psycopg2 uses 'sslmode=require'
if "ssl=require" in database_url:
    database_url = database_url.replace("ssl=require", "sslmode=require")

# Handle special characters in database URL for ConfigParser
# Parse the URL to properly encode the password component
try:
    parsed = urllib.parse.urlparse(database_url)
    if parsed.password and any(char in parsed.password for char in ['%', '(', ')', ',', '>', '<', '#']):
        # Reconstruct URL with URL-encoded password
        encoded_password = urllib.parse.quote(parsed.password, safe='')
        database_url = f"{parsed.scheme}://{parsed.username}:{encoded_password}@{parsed.hostname}:{parsed.port}{parsed.path}"
        if parsed.query:
            database_url += f"?{parsed.query}"
except Exception as e:
    # If URL parsing fails, try to set it directly via environment approach
    print(f"Warning: URL parsing failed: {e}, using direct approach")
    # Store URL in environment for engine_from_config to pick up
    os.environ['SQLALCHEMY_URL'] = database_url
    database_url = ""  # Clear for config.set_main_option

if database_url:  # Only set if we have a processed URL
    config.set_main_option("sqlalchemy.url", database_url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    configuration = config.get_section(config.config_ini_section, {})
    
    # If no URL was set via config (due to encoding issues), use environment variable
    if 'sqlalchemy.url' not in configuration or not configuration.get('sqlalchemy.url'):
        configuration['sqlalchemy.url'] = os.environ.get('SQLALCHEMY_URL', database_url)
    
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
