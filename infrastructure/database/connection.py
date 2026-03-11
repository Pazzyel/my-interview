from typing import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from common.config import app_config

# Create async engine instance
engine = create_async_engine(
    app_config.database_url,
    echo=False,
    future=True
)

# Create session factory
async_session_factory = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)

async def get_async_session() -> AsyncGenerator[AsyncSession]: # type: ignore
    """
    Dependency to provide a database session
    """
    async with async_session_factory() as session:
        yield session
