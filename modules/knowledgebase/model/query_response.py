from infrastructure.model.BaseCamelSchema import BaseCamelSchema


class QueryResponse(BaseCamelSchema):
    answer: str
    knowledge_base_id: int
    knowledge_base_name: str