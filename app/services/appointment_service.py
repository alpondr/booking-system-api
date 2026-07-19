from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
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


class AppointmentNotActiveError(Exception):
    """Cancel/reschedule was attempted on a non-active appointment."""


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


def has_overlap(
    db: Session,
    start_time: datetime,
    end_time: datetime,
    exclude_appointment_id: int | None = None,
) -> bool:
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

    exclude_appointment_id is used by reschedule: the appointment being
    moved currently occupies its own old slot, so it must not be counted
    as a conflict against itself.
    """
    query = db.query(Appointment).filter(
        Appointment.status == AppointmentStatus.ACTIVE,
        Appointment.start_time < end_time,
        Appointment.end_time > start_time,
    )
    if exclude_appointment_id is not None:
        query = query.filter(Appointment.id != exclude_appointment_id)

    return query.first() is not None


def validate_appointment_time(
    db: Session,
    start_time: datetime,
    end_time: datetime,
    exclude_appointment_id: int | None = None,
) -> None:
    if is_in_the_past(start_time):
        raise AppointmentInPastError("Cannot book an appointment in the past")

    if not is_within_working_hours(start_time, end_time):
        raise OutsideWorkingHoursError(
            f"Appointments must fit within working hours "
            f"({WORKING_HOURS_START.strftime('%H:%M')}-{WORKING_HOURS_END.strftime('%H:%M')} "
            f"{BUSINESS_TIMEZONE.key})"
        )

    if has_overlap(db, start_time, end_time, exclude_appointment_id=exclude_appointment_id):
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


def cancel_appointment(db: Session, appointment: Appointment) -> Appointment:
    # Soft delete: flip the status, never remove the row. Keeps the
    # appointment's history around (for the admin views in the next step)
    # instead of destroying data that already happened.
    if appointment.status != AppointmentStatus.ACTIVE:
        raise AppointmentNotActiveError("Only active appointments can be cancelled")

    appointment.status = AppointmentStatus.CANCELLED
    db.commit()
    db.refresh(appointment)
    return appointment


def reschedule_appointment(
    db: Session, appointment: Appointment, new_start_time: datetime
) -> Appointment:
    if appointment.status != AppointmentStatus.ACTIVE:
        raise AppointmentNotActiveError("Only active appointments can be rescheduled")

    # Keep the originally booked duration, even if the service's default
    # duration has since changed - the customer agreed to this length.
    duration = appointment.end_time - appointment.start_time
    new_end_time = new_start_time + duration

    validate_appointment_time(
        db, new_start_time, new_end_time, exclude_appointment_id=appointment.id
    )

    appointment.start_time = new_start_time
    appointment.end_time = new_end_time
    db.commit()
    db.refresh(appointment)
    return appointment


def _local_day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    """Turns a calendar day (business's local timezone) into a
    [start, end) UTC datetime range, for filtering start_time by date."""
    start_local = datetime.combine(day, time.min, tzinfo=BUSINESS_TIMEZONE)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def list_user_appointments(
    db: Session,
    user_id: int,
    time_filter: Literal["past", "upcoming"] | None,
    page: int,
    page_size: int,
) -> tuple[list[Appointment], int]:
    query = db.query(Appointment).filter(Appointment.user_id == user_id)

    now = datetime.now(timezone.utc)
    if time_filter == "past":
        query = query.filter(Appointment.start_time < now)
    elif time_filter == "upcoming":
        query = query.filter(Appointment.start_time >= now)

    total = query.count()
    items = (
        query.order_by(Appointment.start_time)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def list_all_appointments(
    db: Session,
    status_filter: AppointmentStatus | None,
    date_from: date | None,
    date_to: date | None,
    page: int,
    page_size: int,
) -> tuple[list[Appointment], int]:
    query = db.query(Appointment)

    if status_filter is not None:
        query = query.filter(Appointment.status == status_filter)
    if date_from is not None:
        start_utc, _ = _local_day_bounds_utc(date_from)
        query = query.filter(Appointment.start_time >= start_utc)
    if date_to is not None:
        _, end_utc = _local_day_bounds_utc(date_to)
        query = query.filter(Appointment.start_time < end_utc)

    total = query.count()
    items = (
        query.order_by(Appointment.start_time)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def _working_hours_window_utc(day: date) -> tuple[datetime, datetime]:
    """Working hours (09:00-18:00 local) for one calendar day, in UTC."""
    start_local = datetime.combine(day, WORKING_HOURS_START, tzinfo=BUSINESS_TIMEZONE)
    end_local = datetime.combine(day, WORKING_HOURS_END, tzinfo=BUSINESS_TIMEZONE)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def find_available_slots(
    db: Session, service: Service, day: date
) -> list[tuple[datetime, datetime]]:
    """
    Free-time-between-busy-intervals scan:

    1. Start with one big "free" window: working hours for that day.
    2. Fetch every ACTIVE appointment that overlaps that window, sorted by
       start_time - these are the "busy" intervals.
    3. Walk through them left to right with a moving `cursor`. Any gap
       between the cursor and the next busy interval's start is free time;
       chop that gap into back-to-back slots the length of this service's
       duration. Then jump the cursor past the busy interval
       (cursor = max(cursor, busy.end) - the max() matters if a later
       appointment is fully contained inside an earlier one).
    4. Whatever's left after the last busy interval, up to closing time,
       is free too.

    This is the same "merge/scan intervals" pattern behind classic
    "meeting rooms" / "find free time" interview questions.
    """
    window_start, window_end = _working_hours_window_utc(day)

    now = datetime.now(timezone.utc)
    if window_start < now:
        window_start = now  # don't offer slots that are already in the past

    duration = timedelta(minutes=service.duration_minutes)

    busy_appointments = (
        db.query(Appointment)
        .filter(
            Appointment.status == AppointmentStatus.ACTIVE,
            Appointment.start_time < window_end,
            Appointment.end_time > window_start,
        )
        .order_by(Appointment.start_time)
        .all()
    )

    def slots_in_gap(gap_start: datetime, gap_end: datetime) -> list[tuple[datetime, datetime]]:
        slots = []
        slot_start = gap_start
        while slot_start + duration <= gap_end:
            slots.append((slot_start, slot_start + duration))
            slot_start += duration
        return slots

    free_slots: list[tuple[datetime, datetime]] = []
    cursor = window_start

    for appointment in busy_appointments:
        if cursor < appointment.start_time:
            free_slots += slots_in_gap(cursor, min(appointment.start_time, window_end))
        cursor = max(cursor, appointment.end_time)
        if cursor >= window_end:
            break

    if cursor < window_end:
        free_slots += slots_in_gap(cursor, window_end)

    return free_slots
