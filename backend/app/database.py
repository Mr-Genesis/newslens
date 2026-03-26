import ssl as ssl_module

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# For cloud databases (Neon/Supabase) that require SSL,
# pass ssl context via connect_args since asyncpg doesn't accept
# sslmode as a URL query param through SQLAlchemy.
_connect_args = {}
if "neon.tech" in settings.database_url or "supabase" in settings.database_url:
    _ssl_context = ssl_module.create_default_context()
    _ssl_context.check_hostname = False
    _ssl_context.verify_mode = ssl_module.CERT_NONE
    _connect_args["ssl"] = _ssl_context

engine = create_async_engine(
    settings.database_url, echo=False, pool_pre_ping=True,
    connect_args=_connect_args,
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def check_db_health() -> bool:
    try:
        async with async_session() as session:
            await session.execute("SELECT 1")
            return True
    except Exception:
        return False
