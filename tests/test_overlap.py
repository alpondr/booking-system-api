"""Overlap detection, tested at the service layer.

Every case here is built around one existing appointment at 10:00-10:30
(business local time), and asks: does a second range collide with it?

The rule under test is half-open intervals - [start, end) - so an
appointment that ends exactly when another begins is NOT a conflict.
That single boundary decision is what makes back-to-back bookings
possible, and it's the easiest thing to break with an accidental <= .
"""

from datetime import timedelta

import pytest

from app.models.appointment import AppointmentStatus
from app.services.appointment_service import (
    AppointmentInPastError,
    AppointmentOverlapError,
    OutsideWorkingHoursError,
    has_overlap,
    validate_appointment_time,
)
from tests.utils import at, past_at


@pytest.fixture
def existing(appointment_factory):
    """One active appointment, 10:00-10:30 local, tomorrow."""
    return appointment_factory(at(10, 0))


# --- boundaries ---


def test_starting_exactly_when_the_other_ends_is_allowed(db_session, existing):
    assert has_overlap(db_session, at(10, 30), at(11, 0)) is False


def test_ending_exactly_when_the_other_starts_is_allowed(db_session, existing):
    assert has_overlap(db_session, at(9, 30), at(10, 0)) is False


def test_one_minute_into_the_end_of_the_other_conflicts(db_session, existing):
    assert has_overlap(db_session, at(9, 31), at(10, 1)) is True


def test_one_minute_before_the_start_of_the_other_conflicts(db_session, existing):
    assert has_overlap(db_session, at(10, 29), at(10, 59)) is True


def test_fully_inside_the_other_conflicts(db_session, existing):
    assert has_overlap(db_session, at(10, 5), at(10, 20)) is True


def test_fully_containing_the_other_conflicts(db_session, existing):
    assert has_overlap(db_session, at(9, 0), at(11, 0)) is True


def test_identical_range_conflicts(db_session, existing):
    assert has_overlap(db_session, at(10, 0), at(10, 30)) is True


def test_a_clearly_separate_range_does_not_conflict(db_session, existing):
    assert has_overlap(db_session, at(14, 0), at(14, 30)) is False


def test_same_clock_time_on_another_day_does_not_conflict(db_session, existing):
    assert has_overlap(db_session, at(10, 0, days_ahead=2), at(10, 30, days_ahead=2)) is False


# --- status and self-exclusion ---


def test_cancelled_appointments_free_their_slot(db_session, appointment_factory):
    appointment_factory(at(10, 0), status=AppointmentStatus.CANCELLED)
    assert has_overlap(db_session, at(10, 0), at(10, 30)) is False


def test_completed_appointments_also_free_their_slot(db_session, appointment_factory):
    # Only ACTIVE blocks. COMPLETED is in the past anyway, but the query
    # filters on status explicitly, so pin that behaviour down.
    appointment_factory(at(10, 0), status=AppointmentStatus.COMPLETED)
    assert has_overlap(db_session, at(10, 0), at(10, 30)) is False


def test_an_appointment_does_not_conflict_with_itself(db_session, existing):
    """What reschedule relies on: the row being moved still occupies its
    old slot in the DB, so it has to be excluded from the check."""
    assert (
        has_overlap(db_session, at(10, 0), at(10, 30), exclude_appointment_id=existing.id)
        is False
    )


def test_excluding_one_appointment_still_sees_the_others(db_session, existing, appointment_factory):
    other = appointment_factory(at(12, 0))
    assert has_overlap(db_session, at(12, 0), at(12, 30), exclude_appointment_id=existing.id) is True
    assert other.id != existing.id


# --- validate_appointment_time: which error wins ---


def test_overlap_raises(db_session, existing):
    with pytest.raises(AppointmentOverlapError):
        validate_appointment_time(db_session, at(10, 15), at(10, 45))


def test_past_start_time_raises(db_session):
    with pytest.raises(AppointmentInPastError):
        validate_appointment_time(db_session, past_at(10), past_at(10) + timedelta(minutes=30))


def test_before_opening_hours_raises(db_session):
    with pytest.raises(OutsideWorkingHoursError):
        validate_appointment_time(db_session, at(8, 30), at(9, 0))


def test_running_past_closing_time_raises(db_session):
    with pytest.raises(OutsideWorkingHoursError):
        validate_appointment_time(db_session, at(17, 45), at(18, 15))


def test_starting_exactly_at_opening_is_allowed(db_session):
    validate_appointment_time(db_session, at(9, 0), at(9, 30))


def test_ending_exactly_at_closing_is_allowed(db_session):
    validate_appointment_time(db_session, at(17, 30), at(18, 0))


def test_spanning_midnight_raises(db_session):
    """Working hours are checked per calendar day, so a range that lands
    on two different local dates can never be valid."""
    with pytest.raises(OutsideWorkingHoursError):
        validate_appointment_time(db_session, at(23, 30), at(0, 30, days_ahead=2))
