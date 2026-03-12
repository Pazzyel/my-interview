import logging
from typing import List, Optional

from common.exceptions import BusinessException, ErrorCode
from modules.knowledgebase.model.knowledgebase_entity import KnowledgeBaseEntity, VectorStatus
from modules.knowledgebase.repository.knowledgebase_repository import KnowledgeBaseRepository

logger = logging.getLogger(__name__)

class KnowledgeBaseCountService:
    """
    知识库计数服务
    负责更新知识库被提问的次数。
    
    KnowledgeBase count service.
    Responsible for updating the question count of knowledge bases.
    """
    def __init__(self, knowledgebase_repository: KnowledgeBaseRepository):
        self.knowledgebase_repository = knowledgebase_repository

    async def update_question_counts(self, knowledge_base_ids: List[int]) -> None:
        """
        批量更新知识库提问计数
        每个知识库的 question_count +1，表示该知识库参与回答的次数
        
        Batch update question count for knowledge bases.
        Each knowledge base's question_count +1, indicating it participated in answering.
        """
        if not knowledge_base_ids:
            return

        # 去重 / Deduplicate
        unique_ids = list(set(knowledge_base_ids))

        # 验证所有知识库是否存在 / Validate if all knowledge bases exist
        # 实际实现中，这里为了优化可以仅验证，但在高并发下，直接更新也可以。
        # 这里仅作简单校验
        updated_count = await self.knowledgebase_repository.increment_question_count_batch(unique_ids)
        
        if updated_count < len(unique_ids):
            logger.warning(f"部分知识库不存在或未更新成功: 请求更新数量={len(unique_ids)}, 实际更新数量={updated_count}")

        logger.debug(f"批量更新知识库提问计数: ids={unique_ids}, updated={updated_count}")
