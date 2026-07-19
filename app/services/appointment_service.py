from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.appointment import Appointment, AppointmentStatus
from app.models.service import Service

# The business (e.g. the salon) operates on this local timezone.
# "Working hours" is a wall-clock concept -> it only makes sense relative
# to a specific place, so we convert UTC-ish input into this zone before
# checking it, even though everything is *stored* in UTC.
BUSINESS_TIMEZONE = ZoneInfo("Europe/Istanbul")
WORKING_HOURS_START = time(9, 0)
WORKING_HOURS_END = time(18, 0)


class AppointmentInPastError(Exception):
    """start_time is before the current moment."""


class OutsideWorkingHoursError(Exception):
    """The [start_time, end_time) range doesn't fit inside working hours."""


class AppointmentOverlapError(Exception):
    """The requested range overlaps an existing active appointment."""


def calculate_end_time(start_time: datetime, service: Service) -> datetime:
    return start_time + timedelta(minutes=service.duration_minutes)


def is_in_the_past(start_time: datetime) -> bool:
    return start_time < datetime.now(timezone.utc)


def is_within_working_hours(start_time: datetime, end_time: datetime) -> bool:
    # .astimezone() converts to Istanbul local time regardless of what
    # offset the input datetime originally carried.
    local_start = start_time.astimezone(BUSINESS_TIMEZONE)
    local_end = end_time.astimezone(BUSINESS_TIMEZONE)
    return (
        local_start.date() == local_end.date()
        and WORKING_HOURS_START <= local_start.time()
        and local_end.time() <= WORKING_HOURS_END
    )


def has_overlap(db: Session, start_time: datetime, end_time: datetime) -> bool:
    """
    Two half-open ranges [start1, end1) and [start2, end2) overlap exactly
    when:

        start1 < end2  AND  start2 < end1

    Why: they do NOT overlap only in two cases - the new appointment ends
    before/when the existing one starts (end1 <= start2), or it starts
    after/when the existing one ends (start1 >= end2). So:

        no_overlap = (end1 <= start2) OR (start1 >= end2)

    Negate that to get "do they overlap" (De Morgan's law flips OR to AND
    and each <= to > / >= to <):

        overlap = NOT no_overlap = (end1 > start2) AND (start1 < end2)

    which is the same condition written the other way around, and exactly
    what the query below checks against every ACTIVE appointment already
    in the DB. Only ACTIVE ones count - a cancelled appointment must not
    block a new booking for that same slot.
    """
    existing = (
        db.query(Appointment)
        .filter(
            Appointment.status == AppointmentStatus.ACTIVE,
            Appointment.start_time < end_time,
            Appointment.end_time > start_time,
        )
        .first()
    )
    return existing is not None


def validate_appointment_time(db: Session, start_time: datetime, end_time: datetime) -> None:
    if is_in_the_past(start_time):
        raise AppointmentInPastError("Cannot book an appointment in the past")

    if not is_within_working_hours(start_time, end_time):
        raise OutsideWorkingHoursError(
            f"Appointments must fit within working hours "
            f"({WORKING_HOURS_START.strftime('%H:%M')}-{WORKING_HOURS_END.strftime('%H:%M')} "
            f"{BUSINESS_TIMEZONE.key})"
        )

    if has_overlap(db, start_time, end_time):
        raise AppointmentOverlapError("This time slot overlaps with an existing appointment")


def create_appointment(
    db: Session, user_id: int, service: Service, start_time: datetime
) -> Appointment:
    end_time = calculate_end_time(start_time, service)
    validate_appointment_time(db, start_time, end_time)

    appointment = Appointment(
        user_id=user_id,
        service_id=service.id,
        start_time=start_time,
        end_time=end_time,
        status=AppointmentStatus.ACTIVE,
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    return appointment
