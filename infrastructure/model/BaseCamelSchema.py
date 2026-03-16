from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class BaseCamelSchema(BaseModel):
    """配置从后端到前端的camelCase转换"""
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,  # 顺便把支持 SQLAlchemy ORM 解析也开启了
        serialize_by_alias = True
    )