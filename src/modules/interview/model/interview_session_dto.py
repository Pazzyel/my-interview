from enum import Enum

class SessionStatus(Enum):
    """模拟面试会话状态"""
    CREATED = 0
    IN_PROGRESS = 1
    COMPLETED = 2
    EVALUATED = 3