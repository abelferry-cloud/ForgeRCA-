"""PostgreSQL connections use structured settings, never a logged DSN."""

import sqlalchemy as sa

from app.config import Settings


def database_url(settings=None):
    settings = settings or Settings.from_env(required=("POSTGRES_PASSWORD",))
    if not settings.postgres_password:
        raise ValueError("POSTGRES_PASSWORD is required")
    credentials = dict([("password", settings.postgres_password.reveal())])
    return sa.URL.create("postgresql+psycopg", username=settings.postgres_user,
                         host=settings.postgres_host, port=settings.postgres_port,
                         database=settings.postgres_db, **credentials)


def create_db_engine(settings=None):
    return sa.create_engine(database_url(settings), hide_parameters=True, pool_pre_ping=True,
                            connect_args={"connect_timeout": 10})
