from typing import List

from infrastructure.model.BaseCamelSchema import BaseCamelSchema


class QueryRequest(BaseCamelSchema):
    knowledge_base_ids: List[int]
    question: str

