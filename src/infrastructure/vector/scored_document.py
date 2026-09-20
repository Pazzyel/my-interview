from dataclasses import dataclass

from langchain_core.documents import Document


@dataclass(frozen=True)
class ScoredDocument:
    document: Document
    score: float
    rank: int

