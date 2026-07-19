from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


# Generic paginated response wrapper, reused by any "list" endpoint.
# e.g. Page[AppointmentOut] -> {"items": [...], "total": 42, "page": 1, "page_size": 10}
class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
