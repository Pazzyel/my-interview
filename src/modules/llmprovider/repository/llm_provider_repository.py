from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database.models import (
    LlmGlobalSettingORM,
    LlmProviderConfigORM,
    VoiceProviderConfigORM,
)


class LlmProviderRepository:
    async def count(self, db: AsyncSession) -> int:
        return int((await db.scalar(select(func.count()).select_from(LlmProviderConfigORM))) or 0)

    async def list(self, db: AsyncSession) -> list[LlmProviderConfigORM]:
        return list((await db.scalars(select(LlmProviderConfigORM).order_by(LlmProviderConfigORM.id))).all())

    async def get(self, db: AsyncSession, provider_id: str) -> LlmProviderConfigORM | None:
        return await db.get(LlmProviderConfigORM, provider_id)

    async def add(self, db: AsyncSession, provider: LlmProviderConfigORM) -> None:
        db.add(provider)
        await db.flush()

    async def delete(self, db: AsyncSession, provider: LlmProviderConfigORM) -> None:
        await db.delete(provider)
        await db.flush()

    async def get_settings(self, db: AsyncSession) -> LlmGlobalSettingORM | None:
        return await db.get(LlmGlobalSettingORM, 1)

    async def save_settings(self, db: AsyncSession, settings: LlmGlobalSettingORM) -> None:
        db.add(settings)
        await db.flush()


class VoiceProviderConfigRepository:
    async def get(self, db: AsyncSession) -> VoiceProviderConfigORM | None:
        return await db.get(VoiceProviderConfigORM, 1)

    async def save(self, db: AsyncSession, config: VoiceProviderConfigORM) -> None:
        db.add(config)
        await db.flush()
