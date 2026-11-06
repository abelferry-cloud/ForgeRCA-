"""Migrations use the same PostgreSQL settings as the application."""

from alembic import context

from app.db.connection import create_db_engine
from app.db.schema import metadata

if context.is_offline_mode():
    context.configure(dialect_name="postgresql", target_metadata=metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_db_engine()
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=metadata,
                              compare_type=True, compare_server_default=True)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
