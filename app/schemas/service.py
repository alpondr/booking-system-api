from pydantic import BaseModel, ConfigDict, Field


class ServiceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    duration_minutes: int = Field(..., gt=0)


class ServiceCreate(ServiceBase):
    pass


# All fields optional, so admin can update just one field (e.g. only rename)
class ServiceUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    duration_minutes: int | None = Field(None, gt=0)


class ServiceOut(ServiceBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
