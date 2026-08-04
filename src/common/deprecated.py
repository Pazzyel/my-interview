import functools
import inspect
import warnings
from collections.abc import Callable
from typing import Any, TypeVar, cast


F = TypeVar("F", bound=Callable[..., Any])


def deprecated(reason: str) -> Callable[[F], F]:
    """Mark a sync or async callable as deprecated and warn when invoked."""

    def decorator(func: F) -> F:
        message = f"{func.__qualname__} is deprecated: {reason}"
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                warnings.warn(message, DeprecationWarning, stacklevel=2)
                return await func(*args, **kwargs)

            return cast(F, async_wrapper)

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            warnings.warn(message, DeprecationWarning, stacklevel=2)
            return func(*args, **kwargs)

        return cast(F, sync_wrapper)

    return decorator
