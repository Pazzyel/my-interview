import logging
from typing import List

from langchain_core.documents import Document

from common.config import app_config
from common.exceptions import BusinessException, ErrorCode
from infrastructure.vector.scored_document import ScoredDocument
from infrastructure.vector.vector_service import VectorService
from modules.knowledgebase.service.knowledgebase_chunking_service import KnowledgeBaseChunkingService

logger = logging.getLogger(__name__)

class KnowledgeBaseVectorService:
    def __init__(
        self,
        vector_service: VectorService,
        chunking_service: KnowledgeBaseChunkingService | None = None,
    ):
        self.vector_service: VectorService = vector_service
        self.chunking_service = chunking_service or KnowledgeBaseChunkingService()


    async def vectorize_and_store(self, kb_id: int, kb_name: str, kb_category: str, content: str) -> None:
        """
        向量化知识库并存储到 Milvus。
        """
        logger.info("开始向量化知识库: kb_id=%s, content_length=%s", kb_id, len(content))
        try:
            # 1. 先删除该知识库的旧向量数据
            await self.delete_knowledgebase_by_id(kb_id)

            # 2. 文本分块，添加元数据
            documents = self.chunking_service.split(content, kb_id, kb_name, kb_category)

            logger.info("文本分块完成: %s 个 chunks", len(documents))

            # 3. 分批向量化并存储（嵌入模型 API 限制 batch size）
            total_chunks = len(documents)
            batch_size = app_config.kb_embedding_batch_size
            batch_count = (total_chunks + batch_size - 1) // batch_size  # 向上取整
            logger.info(
                "开始分批向量化: 总共 %s 个 chunks，分 %s 批处理，每批最多 %s 个",
                total_chunks, batch_count, batch_size,
            )

            for i in range(batch_count):
                start = i * batch_size
                end = min(start + batch_size, total_chunks)
                batch = documents[start:end]
                logger.debug("处理第 %s/%s 批: chunks %s-%s, 第一篇文档长度=%s", i + 1, batch_count, start + 1, end, len(batch[0].page_content))
                await self.vector_service.add_documents(batch)

            logger.info(
                "知识库向量化完成: kb_id=%s, chunks=%s, batches=%s",
                kb_id, total_chunks, batch_count,
            )

        except BusinessException:
            raise
        except Exception as e:
            logger.error("向量化知识库失败: kb_id=%s, error=%s", kb_id, str(e))
            raise BusinessException(ErrorCode.KB_VECTORIZE_ERROR, "向量化知识库失败", str(e))

    async def similar_search(self, query: str, knowledgebase_ids: List[int], top_k: int, min_score: float) -> List[Document]:
        """
        基于多个知识库进行相似度搜索。

        :param query: 查询文本
        :param knowledgebase_ids: 知识库 ID 列表（为空则搜索所有）
        :param top_k: 返回 top K 个结果
        :param min_score: 最低相似度阈值
        :return: 相关文档列表
        """
        logger.info(
            "向量相似度搜索: query=%s, kb_ids=%s, top_k=%s, min_score=%s",
            query, knowledgebase_ids, top_k, min_score,
        )

        try:
            results = await self.vector_service.similar_search(
                query=query,
                knowledgebase_ids=knowledgebase_ids,
                top_k=top_k,
                min_score=min_score,
            )

            logger.info("搜索完成: 找到 %s 个相关文档", len(results))
            return results

        except Exception as e:
            logger.error("向量搜索失败: %s", str(e))
            raise BusinessException(ErrorCode.KB_VECTORIZE_ERROR, "向量搜索失败", str(e))

    async def similar_search_with_scores(
        self,
        query: str,
        knowledgebase_ids: list[int],
        top_k: int,
        min_score: float,
    ) -> list[ScoredDocument]:
        try:
            return await self.vector_service.similar_search_with_scores(
                query=query,
                knowledgebase_ids=knowledgebase_ids,
                top_k=top_k,
                min_score=min_score,
            )
        except Exception as error:
            logger.error("向量搜索失败: %s", error)
            raise BusinessException(
                ErrorCode.KB_VECTORIZE_ERROR, "向量搜索失败", str(error)
            ) from error

    async def delete_knowledgebase_by_id(self, knowledgebase_id: int) -> None:
        """
        删除指定知识库的所有向量数据。
        通过 metadata 中的 kb_id 字段查询并删除。
        """
        logger.info("开始删除知识库向量数据: kb_id=%s", knowledgebase_id)
        try:
            await self.vector_service.delete_by_kb_id(knowledgebase_id)
            logger.info("成功删除知识库向量数据: kb_id=%s", knowledgebase_id)
        except Exception as e:
            logger.error("删除向量数据失败: kb_id=%s, error=%s", knowledgebase_id, str(e))
