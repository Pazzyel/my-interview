from pydantic import BaseModel


class QuestionDistribution(BaseModel):
    project: int
    mysql: int
    redis: int
    java_basic: int
    java_collection: int
    java_concurrent: int
    spring: int
