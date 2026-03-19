from enum import Enum
from pathlib import Path
from typing import Dict, List

import aiofile
import yaml
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.prompts.chat import MessageLikeRepresentation, MessagesPlaceholder
from langchain_core.runnables import RunnableConfig

current_dir = Path(__file__).parent
root_dir = current_dir.parents[2]
prompt_cache: Dict[str, ChatPromptTemplate] = {} # 全局prompt缓存

class Role(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"

async def load_prompt(node_name: str, with_short_memory: bool = False) -> ChatPromptTemplate:
    """
    加载对应名字的提示词文件

    从resources/prompts/{node_name}.yaml加载
    """
    # 有缓存就加载缓存
    if node_name in prompt_cache:
        return prompt_cache[node_name]

    prompt_path: Path = root_dir / "resources" / "prompts" / f"{node_name}.yaml"
    async with aiofile.async_open(prompt_path, "r", encoding="utf-8") as f:
        content = await f.read()
    config = yaml.safe_load(content)

    # 动态构建prompt
    node_config = config.get(node_name)
    messages: List[MessageLikeRepresentation] = []
    # 先加载系统提示词
    if Role.SYSTEM.value in node_config:
        messages.append((Role.SYSTEM.value, node_config[Role.SYSTEM.value]))
    # 再加载历史提示词
    if with_short_memory:
        messages.append(MessagesPlaceholder(variable_name="messages"))
    # 最后加载用户提问
    if Role.USER.value in node_config:
        messages.append((Role.USER.value, node_config[Role.USER.value]))

    prompt = ChatPromptTemplate.from_messages(messages)
    prompt_cache[node_name] = prompt
    return prompt

def has_short_memory(config: RunnableConfig) -> bool:
    return config.get("configurable") is not None and config.get("configurable").get("thread_id") is not None