from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate and evaluate RAG datasets with Ragas")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("generate", "evaluate", "run"):
        command = subparsers.add_parser(name)
        command.add_argument("--kb-ids", required=name in {"generate", "run"})
        command.add_argument("--size", type=int, default=50)
        command.add_argument("--generator-provider", default="default")
        command.add_argument("--evaluator-provider", default="default")
        command.add_argument("--embedding-provider", default="default")
        command.add_argument("--output-dir", default="evaluation/results")
        command.add_argument("--dataset", default=None)
    return parser


def _parse_ids(value: str | None) -> list[int]:
    if not value:
        return []
    ids = list(dict.fromkeys(int(part.strip()) for part in value.split(",") if part.strip()))
    if not ids or any(item <= 0 for item in ids):
        raise ValueError("--kb-ids must contain positive integer IDs")
    return ids


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return str(value)


def build_evaluation_row(case: dict[str, Any], result: Any) -> dict[str, Any]:
    return {
        "user_input": case["user_input"],
        "retrieved_contexts": [hit.content for hit in result.trace.selected_contexts],
        "response": result.answer,
        "reference": case["reference"],
        "reference_contexts": case.get("reference_contexts", []),
    }


async def generate_dataset(args: argparse.Namespace) -> Path:
    """使用LLM自动生成评测数据集"""
    from ragas.testset import TestsetGenerator

    from common.dependencies import (
        file_storage_service,
        knowledgebase_parse_service,
        knowledgebase_repository,
        llm_provider_registry,
    )
    from infrastructure.database.connection import async_session_factory
    from infrastructure.prompt.prompt_service import get_prompt_hash
    from modules.knowledgebase.model.knowledgebase_entity import VectorStatus
    from modules.knowledgebase.service.knowledgebase_chunking_service import KnowledgeBaseChunkingService

    kb_ids = _parse_ids(args.kb_ids)
    if args.size <= 0:
        raise ValueError("--size must be greater than zero")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = Path(args.dataset) if args.dataset else output_dir / "dataset.jsonl"

    # 获取Ragas评测集生成器
    generator_llm = await llm_provider_registry.get_chat_model(args.generator_provider)
    embeddings = await llm_provider_registry.get_embedding_model(args.embedding_provider)
    generator = TestsetGenerator.from_langchain(generator_llm, embeddings)
    chunker = KnowledgeBaseChunkingService()
    # 为每个知识库文档分配评测集合数目
    allocations = [args.size // len(kb_ids)] * len(kb_ids)
    for index in range(args.size % len(kb_ids)):
        allocations[index] += 1

    rows: list[dict[str, Any]] = []
    knowledge_bases: list[dict[str, Any]] = []
    for kb_id, sample_count in zip(kb_ids, allocations):
        if sample_count == 0:
            continue
        async with async_session_factory() as db:
            entity = await knowledgebase_repository.find_by_id(db, kb_id)
        if entity is None:
            raise ValueError(f"Knowledge base does not exist: {kb_id}")
        if entity.vector_status != VectorStatus.COMPLETED:
            raise ValueError(f"Knowledge base is not vectorized: {kb_id}")
        if not entity.storage_key:
            raise ValueError(f"Knowledge base has no stored source file: {kb_id}")

        source_bytes = await file_storage_service.download_file(entity.storage_key)
        content = await knowledgebase_parse_service.parse_content_from_bytes(
            source_bytes, entity.original_filename
        )
        documents = chunker.split(content, kb_id, entity.name, entity.category)
        # 调用generator生成评测集合
        testset = await asyncio.to_thread(
            generator.generate_with_langchain_docs,
            documents,
            testset_size=sample_count,
        )
        generated = testset.to_pandas().to_dict(orient="records")
        for index, generated_row in enumerate(generated, start=1):
            rows.append({
                "case_id": f"kb{kb_id}-{index:04d}",
                "knowledge_base_ids": [kb_id],
                "user_input": str(generated_row.get("user_input", "")), # 输入内容
                "reference": str(generated_row.get("reference", "")),   # 参考回答
                "reference_contexts": _json_value(generated_row.get("reference_contexts", [])), # 参考检索内容
                "generation_metadata": {
                    "synthesizer_name": _json_value(generated_row.get("synthesizer_name")),
                    "generator_provider": args.generator_provider,
                },
            })
        knowledge_bases.append({
            "id": kb_id,
            "file_hash": entity.file_hash,
            "name": entity.name,
            "chunk_count": len(documents),
        })

    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    _validate_dataset(rows)
    dataset_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    manifest = {
        "generated_at": datetime.now().isoformat(),
        "ragas_version": _ragas_version(),
        "sample_count": len(rows),
        "knowledge_bases": knowledge_bases,
        "chunking": chunker.manifest(),
        "generator_provider": args.generator_provider,
        "generator_model": getattr(generator_llm, "model_name", None),
        "embedding_provider": args.embedding_provider,
        "embedding_model": getattr(embeddings, "model", None),
        "prompt_hashes": {
            name: await get_prompt_hash(name)
            for name in (
                "knowledgebase-query-rewrite",
                "knowledgebase-query-system",
                "knowledgebase-query-user",
            )
        },
    }
    (output_dir / "dataset-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return dataset_path


async def evaluate_dataset(args: argparse.Namespace, dataset_path: Path | None = None) -> Path:
    import pandas as pd
    from ragas import EvaluationDataset, aevaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import (
        Faithfulness,
        FactualCorrectness,
        LLMContextPrecisionWithReference,
        LLMContextRecall,
        ResponseRelevancy,
    )
    from ragas.run_config import RunConfig

    from common.dependencies import knowledgebase_query_service, llm_provider_registry
    from modules.knowledgebase.model.rag_trace import RagExecutionRequest, RagRunMode

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    source_path = dataset_path or (Path(args.dataset) if args.dataset else output_dir / "dataset.jsonl")
    rows = [
        json.loads(line)
        for line in source_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    _validate_dataset(rows)
    await knowledgebase_query_service.build_graph(None)

    semaphore = asyncio.Semaphore(4)

    async def execute_case(case: dict[str, Any]) -> tuple[dict[str, Any], str]:
        async with semaphore:
            # 直接调用服务进行评测
            result = await knowledgebase_query_service.execute(RagExecutionRequest(
                question=case["user_input"],
                knowledge_base_ids=case["knowledge_base_ids"],
                run_mode=RagRunMode.EVALUATION,
                record_usage=False,
                trace_required=True,
            ))
            # 注入正常流程的结果
        return build_evaluation_row(case, result), result.trace.trace_id

    executed = await asyncio.gather(*(execute_case(case) for case in rows))
    evaluation_rows = [item[0] for item in executed]
    trace_ids = [item[1] for item in executed]
    evaluator_model = await llm_provider_registry.get_chat_model(args.evaluator_provider)
    evaluator_embeddings = await llm_provider_registry.get_embedding_model(args.embedding_provider)
    # 让ragas启用评测
    result = await aevaluate(
        dataset=EvaluationDataset.from_list(evaluation_rows),
        metrics=[
            Faithfulness(),
            ResponseRelevancy(),
            LLMContextPrecisionWithReference(),
            LLMContextRecall(),
            FactualCorrectness(),
        ],
        llm=LangchainLLMWrapper(evaluator_model),
        embeddings=LangchainEmbeddingsWrapper(evaluator_embeddings),
        run_config=RunConfig(timeout=120, max_retries=3, max_workers=4),
        batch_size=8,
        raise_exceptions=False,
    )
    frame = result.to_pandas()
    frame.insert(0, "case_id", [row["case_id"] for row in rows])
    frame.insert(1, "trace_id", trace_ids)
    metric_columns = [column for column in frame.columns if pd.api.types.is_numeric_dtype(frame[column])]
    if frame[metric_columns].isna().any().any():
        raise RuntimeError("Ragas returned NaN for one or more metrics")

    csv_path = output_dir / "evaluation-results.csv"
    json_path = output_dir / "evaluation-results.json"
    summary_path = output_dir / "evaluation-summary.json"
    frame.to_csv(csv_path, index=False, encoding="utf-8-sig")
    frame.to_json(json_path, orient="records", force_ascii=False, indent=2)
    summary = {
        "evaluated_at": datetime.now().isoformat(),
        "ragas_version": _ragas_version(),
        "sample_count": len(frame),
        "dataset": str(source_path),
        "evaluator_provider": args.evaluator_provider,
        "embedding_provider": args.embedding_provider,
        "scores": {column: float(frame[column].mean()) for column in metric_columns},
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary_path


def _validate_dataset(rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("Evaluation dataset is empty")
    required = {"case_id", "knowledge_base_ids", "user_input", "reference"}
    for index, row in enumerate(rows, start=1):
        missing = required - row.keys()
        if missing:
            raise ValueError(f"Dataset row {index} is missing: {sorted(missing)}")
        if not row["knowledge_base_ids"] or not row["user_input"] or not row["reference"]:
            raise ValueError(f"Dataset row {index} contains empty required values")


def _ragas_version() -> str:
    from importlib.metadata import version

    return version("ragas")


async def _main() -> None:
    args = _parser().parse_args()
    if args.command == "generate":
        path = await generate_dataset(args)
    elif args.command == "evaluate":
        path = await evaluate_dataset(args)
    else:
        dataset_path = await generate_dataset(args)
        path = await evaluate_dataset(args, dataset_path)
    print(path)


if __name__ == "__main__":
    asyncio.run(_main())
