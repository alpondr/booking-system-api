from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.appointment import AppointmentStatus


# Shared by "create" and "reschedule": the client must send a timezone-aware
# timestamp (e.g. "2026-07-21T10:00:00+03:00" or "...Z" for UTC). We reject
# naive datetimes here so an ambiguous time never reaches the DB layer.
class _TimezoneAwareStartTime(BaseModel):
    start_time: datetime

    @field_validator("start_time")
    @classmethod
    def start_time_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError(
                "start_time must include timezone info, e.g. '2026-07-21T10:00:00+03:00'"
            )
        return value


class AppointmentCreate(_TimezoneAwareStartTime):
    service_id: int


class AppointmentReschedule(_TimezoneAwareStartTime):
    pass


class AppointmentOut(BaseModel):
    id: int
    user_id: int
    service_id: int
    start_time: datetime
    end_time: datetime
    status: AppointmentStatus

    model_config = ConfigDict(from_attributes=True)
