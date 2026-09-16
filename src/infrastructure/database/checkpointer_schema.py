import logging
import re
from typing import Any


logger = logging.getLogger(__name__)

CHECKPOINTER_COLLATION = "utf8mb4_0900_ai_ci"
CHECKPOINTER_TABLES = ("checkpoints", "checkpoint_blobs", "checkpoint_writes")


async def normalize_checkpointer_collation(checkpointer: Any) -> None:
    """Align existing checkpoint tables with LangGraph's JSON_TABLE columns."""
    async with checkpointer._cursor() as cursor:
        await cursor.execute("SELECT DATABASE() AS database_name")
        database_row = await cursor.fetchone()
        database_name = _row_value(database_row, "database_name", 0)
        if not isinstance(database_name, str) or re.fullmatch(r"[A-Za-z0-9_]+", database_name) is None:
            raise RuntimeError("Unable to determine a safe checkpointer database name")

        await cursor.execute(
            f"ALTER DATABASE `{database_name}` CHARACTER SET utf8mb4 COLLATE {CHECKPOINTER_COLLATION}"
        )

        for table_name in CHECKPOINTER_TABLES:
            await cursor.execute(
                """
                SELECT COUNT(*) AS mismatch_count
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = %s
                  AND CHARACTER_SET_NAME = 'utf8mb4'
                  AND COLLATION_NAME <> %s
                """,
                (table_name, CHECKPOINTER_COLLATION),
            )
            mismatch_row = await cursor.fetchone()
            mismatch_count = int(_row_value(mismatch_row, "mismatch_count", 0) or 0)
            if mismatch_count == 0:
                continue

            await cursor.execute(
                f"ALTER TABLE `{table_name}` CONVERT TO CHARACTER SET utf8mb4 COLLATE {CHECKPOINTER_COLLATION}"
            )
            logger.info(
                "Normalized LangGraph checkpointer collation: table=%s, collation=%s",
                table_name,
                CHECKPOINTER_COLLATION,
            )


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    if isinstance(row, (list, tuple)) and len(row) > index:
        return row[index]
    return None
