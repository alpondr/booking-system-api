"""Available slot scanning.

find_available_slots walks the day's active appointments in order and
carves the gaps between them into slots. The interesting cases are the
ones where the gaps aren't tidy: appointments that don't line up with the
slot grid, appointments nested inside each other, and "today", where the
window has to be trimmed to now.
"""

from datetime import datetime, timedelta, timezone

from app.models.appointment import AppointmentStatus
from app.services.appointment_service import find_available_slots
from tests.utils import at, local_today

# 09:00-18:00 with a 30 minute service
SLOTS_IN_AN_EMPTY_DAY = 18


def tomorrow():
    return local_today() + timedelta(days=1)


def starts(slots):
    return [start for start, _ in slots]


def test_an_empty_day_is_fully_bookable(db_session, service):
    slots = find_available_slots(db_session, service, tomorrow())

    assert len(slots) == SLOTS_IN_AN_EMPTY_DAY
    assert slots[0] == (at(9, 0), at(9, 30))
    assert slots[-1] == (at(17, 30), at(18, 0))


def test_a_booked_slot_is_removed(db_session, service, appointment_factory):
    appointment_factory(at(10, 0))
    slots = find_available_slots(db_session, service, tomorrow())

    assert len(slots) == SLOTS_IN_AN_EMPTY_DAY - 1
    assert at(10, 0) not in starts(slots)


def test_a_cancelled_appointment_does_not_block_slots(db_session, service, appointment_factory):
    appointment_factory(at(10, 0), status=AppointmentStatus.CANCELLED)
    assert len(find_available_slots(db_session, service, tomorrow())) == SLOTS_IN_AN_EMPTY_DAY


def test_slots_restart_from_the_end_of_a_misaligned_appointment(
    db_session, service, appointment_factory
):
    """An appointment at 10:15-10:45 doesn't sit on the 30 minute grid.
    The gap before it (09:00-10:15) only fits two full slots, and the
    leftover 10:00-10:15 is too short to offer. Afterwards the grid
    restarts at 10:45, not at 11:00 - slots are packed against the gap,
    not against a fixed timetable."""
    appointment_factory(at(10, 15), end_time=at(10, 45))
    slots = starts(find_available_slots(db_session, service, tomorrow()))

    assert slots[:3] == [at(9, 0), at(9, 30), at(10, 45)]


def test_back_to_back_appointments_leave_no_gap(db_session, service, appointment_factory):
    appointment_factory(at(10, 0))
    appointment_factory(at(10, 30))
    slots = starts(find_available_slots(db_session, service, tomorrow()))

    assert at(10, 0) not in slots
    assert at(10, 30) not in slots
    assert at(11, 0) in slots


def test_an_appointment_nested_inside_another_does_not_reopen_the_slot(
    db_session, service, appointment_factory
):
    """A 10:30-11:00 appointment sits entirely inside a 10:00-12:00 one.
    Walking them in order, the cursor is already at 12:00 when the nested
    one is processed - it must not be dragged back to 11:00, which would
    offer slots that are actually busy."""
    appointment_factory(at(10, 0), end_time=at(12, 0))
    appointment_factory(at(10, 30), end_time=at(11, 0))
    slots = starts(find_available_slots(db_session, service, tomorrow()))

    assert at(11, 0) not in slots
    assert at(11, 30) not in slots
    assert at(12, 0) in slots


def test_a_full_day_offers_nothing(db_session, service, appointment_factory):
    appointment_factory(at(9, 0), end_time=at(18, 0))
    assert find_available_slots(db_session, service, tomorrow()) == []


def test_today_never_offers_a_slot_in_the_past(db_session, service):
    """The window starts at max(opening time, now), so slots already gone
    by are not on offer - otherwise the API would suggest times that
    POST /appointments then rejects as being in the past."""
    slots = find_available_slots(db_session, service, local_today())
    now = datetime.now(timezone.utc)
    assert all(start >= now for start in starts(slots))


def test_a_longer_service_gets_fewer_slots(db_session, service_factory):
    long_service = service_factory(name="Full Colour", duration_minutes=90)
    slots = find_available_slots(db_session, long_service, tomorrow())

    assert len(slots) == 6  # 9 hours / 90 minutes
    assert slots[-1] == (at(16, 30), at(18, 0))


# --- through the API ---


def test_available_slots_endpoint_returns_slots(client, service):
    response = client.get(
        f"/services/{service.id}/available-slots", params={"date": tomorrow().isoformat()}
    )
    assert response.status_code == 200
    assert len(response.json()) == SLOTS_IN_AN_EMPTY_DAY


def test_available_slots_are_public(client, service):
    """Browsing has to work before you have an account, otherwise nobody
    can see whether the business has room before signing up."""
    response = client.get(
        f"/services/{service.id}/available-slots", params={"date": tomorrow().isoformat()}
    )
    assert response.status_code == 200


def test_available_slots_rejects_a_past_date(client, service):
    yesterday = local_today() - timedelta(days=1)
    response = client.get(
        f"/services/{service.id}/available-slots", params={"date": yesterday.isoformat()}
    )
    assert response.status_code == 400


def test_available_slots_for_an_unknown_service_is_not_found(client, service):
    response = client.get(
        f"/services/{service.id + 999}/available-slots", params={"date": tomorrow().isoformat()}
    )
    assert response.status_code == 404
