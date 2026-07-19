from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

from config import settings


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _engine_options(
    database_url: str, *, migration: bool = False
) -> dict[str, object]:
    options: dict[str, object] = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
        if database_url.endswith(":memory:"):
            options["poolclass"] = StaticPool
    elif migration:
        options["poolclass"] = NullPool
    else:
        options.update(
            {
                "pool_size": settings.database_pool_size,
                "max_overflow": settings.database_max_overflow,
                "pool_timeout": 30,
                "pool_recycle": 300,
            }
        )
    return options


engine = create_engine(settings.database_url, **_engine_options(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


if settings.database_url.startswith("sqlite"):

    @event.listens_for(Engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection: object, _: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    import models  # noqa: F401

    if settings.database_url_direct == settings.database_url:
        Base.metadata.create_all(bind=engine)
        return

    migration_engine = create_engine(
        settings.database_url_direct,
        **_engine_options(settings.database_url_direct, migration=True),
    )
    try:
        Base.metadata.create_all(bind=migration_engine)
    finally:
        migration_engine.dispose()


if __name__ == "__main__":
    init_db()
    schema_url = make_url(settings.database_url_direct).render_as_string(
        hide_password=True
    )
    print(f"Database tables are ready using {schema_url}")
