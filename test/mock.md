# Mock

Mock的对象应该尽可能少，尽可能底层

如果是Mock了自己编写的类，可能需要有单独的测试

需要被 mock 替换的功能有：

## 1) 数据库读写（SQLAlchemy AsyncSession）

推荐直接用轻量内存数据库sqlite

### 建议 mock 的函数/对象
- `infrastructure.database.connection.get_async_session`
- `infrastructure.database.connection.async_session_factory`
- `AsyncSession` 常用方法（通过 fake session/AsyncMock 提供）：
	- `execute`
	- `add`
	- `flush`
	- `commit`
	- `rollback`

### 说明
- 路由/服务层如果通过依赖注入拿 DB，会走 `get_async_session`。
- 一些 producer 的失败回写逻辑直接使用 `async_session_factory()`（不是 `get_async_session`）。

---

## 2) RustFS 存储（FileStorageService）

建议直接写一个FakeFileStorageService

### 建议 mock 的函数
- `FileStorageService._create_s3_client`
- `FileStorageService.ensure_bucket_exists`
- `FileStorageService.upload_file_to_rustfs`
- `FileStorageService.upload_resume`
- `FileStorageService.upload_knowledgebase`
- `FileStorageService.get_file_url`
- `FileStorageService.download_file`
- `FileStorageService.file_exists`
- `FileStorageService.delete_file`

### 如果做偏集成的 service 单测，还需要 mock 的 S3 client 方法
- `head_bucket`
- `create_bucket`
- `put_object`
- `generate_presigned_url`
- `get_object`
- `head_object`
- `delete_object`

---

## 3) RocketMQ 生产者

建议直接写FakeAbstractMessageProducer，Windows平台需要防止RocketMQ的实际包导入

### 抽象生产者（公共入口）
- `common.async_task.abstract_message_producer.AbstractMessageProducer.send_task`
- `common.async_task.abstract_message_producer.AbstractMessageProducer.shutdown`

> 通常还需要 mock 底层 producer，避免真实网络连接：
- `rocketmq.client.Producer.start`
- `rocketmq.client.Producer.send_sync`
- `rocketmq.client.Producer.shutdown`

### 各业务生产者对外发送函数
- `modules.interview.listener.evaluate_message_producer.EvaluateMessageProducer.send_evaluate_task`
- `modules.resume.listener.analyze_message_producer.AnalyzeMessageProducer.send_analyze_task`
- `modules.knowledgebase.listener.vectorize_message_producer.VectorizeMessageProducer.send_vectorize_task`

### 失败回写（会触发 DB）
- `EvaluateMessageProducer.on_send_failed` / `_update_evaluate_status`
- `AnalyzeMessageProducer.on_send_failed` / `_update_analyze_status`
- `VectorizeMessageProducer.on_send_failed` / `_update_vector_status`

---

## 4) ElasticSearch 向量库（vector_store）

建议使用轻量内存数据库chromaDB，这个类只需要更换数据源

当前的vector_store耦合度比较高，可能需要整体替换？

### 建议 mock 的函数
- `infrastructure.vector.vector_store.vector_store`（可整体替换成 AsyncMock 对象）

### 在知识库向量服务中的实际调用点
- `modules.knowledgebase.service.knowledgebase_vector_service.vector_store.aadd_documents`
- `modules.knowledgebase.service.knowledgebase_vector_service.vector_store.asimilarity_search_with_score`
- `modules.knowledgebase.service.knowledgebase_vector_service.vector_store.client.delete_by_query`

### 说明
- `KnowledgeBaseVectorService` 文件里是 `from ... import vector_store`，
	测试时优先 patch `knowledgebase_vector_service` 模块内的 `vector_store` 引用。

---

## 快速建议（单测优先级）

1. **业务单测（推荐）**：直接 mock service/repository/producer 的对外方法（最稳定）。
2. **组件单测**：mock `send_task`、`upload_file_to_rustfs`、`vector_store.*`。
3. **底层适配单测**：再 mock `AsyncSession`、`S3 client`、`Producer.send_sync` 等细粒度方法。
