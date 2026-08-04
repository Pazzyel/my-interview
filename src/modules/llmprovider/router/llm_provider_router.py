from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from common.dependencies import llm_provider_service
from common.models import Result
from infrastructure.database.connection import get_async_session
from modules.llmprovider.model.llm_provider_dto import (
    DefaultProviderDTO,
    LlmProviderCreateRequest,
    LlmProviderDTO,
    LlmProviderUpdateRequest,
    ProviderTestResultDTO,
)

router = APIRouter(prefix="/api/llm-provider", tags=["LLM Provider"])


@router.get("/list", response_model=Result[list[LlmProviderDTO]])
async def list_providers(db: AsyncSession = Depends(get_async_session)):
    return Result.success(await llm_provider_service.list(db))


@router.post("/reload", response_model=Result[None])
async def reload_providers():
    await llm_provider_service.reload()
    return Result.success(message="Provider 缓存已刷新")


@router.get("/default-provider", response_model=Result[DefaultProviderDTO])
async def get_defaults(db: AsyncSession = Depends(get_async_session)):
    return Result.success(await llm_provider_service.defaults(db))


@router.put("/default-provider", response_model=Result[DefaultProviderDTO])
async def set_default_provider(
    request: DefaultProviderDTO,
    db: AsyncSession = Depends(get_async_session),
):
    return Result.success(await llm_provider_service.set_default_chat(db, request.default_provider))


@router.put("/default-embedding-provider", response_model=Result[DefaultProviderDTO])
async def set_default_embedding_provider(
    request: DefaultProviderDTO,
    db: AsyncSession = Depends(get_async_session),
):
    return Result.success(
        await llm_provider_service.set_default_embedding(db, request.default_embedding_provider)
    )


@router.post("", response_model=Result[LlmProviderDTO])
async def create_provider(
    request: LlmProviderCreateRequest,
    db: AsyncSession = Depends(get_async_session),
):
    return Result.success(await llm_provider_service.create(db, request))


@router.get("/{provider_id}", response_model=Result[LlmProviderDTO])
async def get_provider(provider_id: str, db: AsyncSession = Depends(get_async_session)):
    return Result.success(await llm_provider_service.get(db, provider_id))


@router.put("/{provider_id}", response_model=Result[LlmProviderDTO])
async def update_provider(
    provider_id: str,
    request: LlmProviderUpdateRequest,
    db: AsyncSession = Depends(get_async_session),
):
    return Result.success(await llm_provider_service.update(db, provider_id, request))


@router.delete("/{provider_id}", response_model=Result[None])
async def delete_provider(provider_id: str, db: AsyncSession = Depends(get_async_session)):
    await llm_provider_service.delete(db, provider_id)
    return Result.success()


@router.post("/{provider_id}/test", response_model=Result[ProviderTestResultDTO])
async def test_provider(provider_id: str, db: AsyncSession = Depends(get_async_session)):
    return Result.success(await llm_provider_service.test(db, provider_id))
