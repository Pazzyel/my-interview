import logging
from typing import List

import tiktoken
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from common.config import app_config
from common.exceptions import BusinessException, ErrorCode
from infrastructure.vector.vector_store import vector_store

logger = logging.getLogger(__name__)

tokenizer = tiktoken.get_encoding(app_config.tokenizer_name)

# 嵌入模型 API 批量大小限制
MAX_BATCH_SIZE = 10

def token_length_function(content: str) -> int:
    """
    返回文本计算的token长度
    """
    return len(tokenizer.encode(content))



class KnowledgeBaseVectorService:
    def __init__(self):
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,           # 每个块 500 Tokens
            chunk_overlap=50,         # 重叠 50 Tokens
            length_function=token_length_function, # 核心：按 Token 计长
            separators=["\n\n", "\n", "。", "！", "？", "；", " ", ""] # 针对中文优化
        )


    def vectorize_and_store(self, kb_id: int, kb_name: str, kb_category: str, content: str) -> None:
        """
        向量化知识库并存储到 Elasticsearch。
        """
        logger.info("开始向量化知识库: kb_id=%s, content_length=%s", kb_id, len(content))
        try:
            # 1. 先删除该知识库的旧向量数据
            self.delete_knowledgebase_by_id(kb_id)

            # 2. 文本分块，添加元数据
            documents: List[Document] = self.text_splitter.create_documents([content])
            for document in documents:
                document.metadata = {
                    "kb_id": str(kb_id),  # 统一使用 String 类型存储，确保查询一致性
                    "source": kb_name,  # 溯源显示
                    "category": kb_category or "general",  # 用于搜索过滤
                }

            logger.info("文本分块完成: %s 个 chunks", len(documents))

            # 3. 分批向量化并存储（嵌入模型 API 限制 batch size）
            total_chunks = len(documents)
            batch_count = (total_chunks + MAX_BATCH_SIZE - 1) // MAX_BATCH_SIZE  # 向上取整
            logger.info(
                "开始分批向量化: 总共 %s 个 chunks，分 %s 批处理，每批最多 %s 个",
                total_chunks, batch_count, MAX_BATCH_SIZE,
            )

            for i in range(batch_count):
                start = i * MAX_BATCH_SIZE
                end = min(start + MAX_BATCH_SIZE, total_chunks)
                batch = documents[start:end]
                logger.debug("处理第 %s/%s 批: chunks %s-%s", i + 1, batch_count, start + 1, end)
                vector_store.add_documents(batch)

            logger.info(
                "知识库向量化完成: kb_id=%s, chunks=%s, batches=%s",
                kb_id, total_chunks, batch_count,
            )

        except BusinessException:
            raise
        except Exception as e:
            logger.error("向量化知识库失败: kb_id=%s, error=%s", kb_id, str(e))
            raise BusinessException(ErrorCode.KB_VECTORIZE_ERROR, "向量化知识库失败", str(e))

    def delete_knowledgebase_by_id(self, knowledgebase_id: int) -> None:
        """
        删除指定知识库的所有向量数据。
        通过 metadata 中的 kb_id 字段查询并删除。
        """
        logger.info("开始删除知识库向量数据: kb_id=%s", knowledgebase_id)
        try:
            # 使用 Elasticsearch 客户端按 metadata.kb_id 删除
            es_client = vector_store.client
            index_name = app_config.elasticsearch_index_name

            # metadata.kb_id.keyword: keyword存储原始值，不做任何分析，用于精确匹配
            es_client.delete_by_query(
                index=index_name,
                body={
                    "query": {
                        "term": {
                            "metadata.kb_id.keyword": str(knowledgebase_id)
                        }
                    }
                },
                refresh=True,
            )
            logger.info("成功删除知识库向量数据: kb_id=%s", knowledgebase_id)
        except Exception as e:
            logger.error("删除向量数据失败: kb_id=%s, error=%s", knowledgebase_id, str(e))