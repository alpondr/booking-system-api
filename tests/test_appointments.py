"""Booking, cancelling and rescheduling over HTTP.

test_overlap.py already pins down the interval logic itself. What matters
here is the translation layer: does each service-level error come back as
the right status code, and does the endpoint behave end to end.
"""

from datetime import timedelta

from app.models.appointment import AppointmentStatus
from tests.utils import at, iso, parse, past_at


def book(client, service, start_time):
    return client.post(
        "/appointments", json={"service_id": service.id, "start_time": iso(start_time)}
    )


# --- booking ---


def test_booking_returns_the_created_appointment(user_client, service, user):
    start = at(10, 0)
    response = book(user_client, service, start)

    assert response.status_code == 201
    body = response.json()
    assert body["user_id"] == user.id
    assert body["status"] == AppointmentStatus.ACTIVE.value
    # end_time is derived from the service duration, never sent by the client
    assert parse(body["end_time"]) == start + timedelta(minutes=service.duration_minutes)


def test_booking_over_an_existing_appointment_conflicts(user_client, service, appointment_factory):
    appointment_factory(at(10, 0))
    assert book(user_client, service, at(10, 15)).status_code == 409


def test_booking_back_to_back_is_allowed(user_client, service, appointment_factory):
    appointment_factory(at(10, 0))
    assert book(user_client, service, at(10, 30)).status_code == 201


def test_booking_over_another_users_appointment_conflicts(
    user_client, service, appointment_factory, other_user
):
    """Single-provider business: the slot is taken regardless of who took it."""
    appointment_factory(at(10, 0), owner=other_user)
    assert book(user_client, service, at(10, 0)).status_code == 409


def test_booking_in_the_past_is_rejected(user_client, service):
    assert book(user_client, service, past_at(10)).status_code == 400


def test_booking_outside_working_hours_is_rejected(user_client, service):
    assert book(user_client, service, at(8, 0)).status_code == 400


def test_booking_that_runs_past_closing_is_rejected(user_client, service):
    assert book(user_client, service, at(17, 45)).status_code == 400


def test_booking_rejects_a_naive_datetime(user_client, service):
    """Without an offset the instant is ambiguous, so the schema refuses
    it before any of the business rules even run."""
    response = user_client.post(
        "/appointments",
        json={"service_id": service.id, "start_time": at(10, 0).replace(tzinfo=None).isoformat()},
    )
    assert response.status_code == 422


def test_booking_an_unknown_service_is_not_found(user_client, service):
    response = user_client.post(
        "/appointments", json={"service_id": service.id + 999, "start_time": iso(at(10, 0))}
    )
    assert response.status_code == 404


def test_booking_requires_authentication(client, service):
    assert book(client, service, at(10, 0)).status_code == 401


# --- cancel ---


def test_cancelling_sets_the_status_without_deleting(user_client, appointment_factory, db_session):
    appointment = appointment_factory(at(10, 0))
    response = user_client.post(f"/appointments/{appointment.id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == AppointmentStatus.CANCELLED.value
    # Soft delete: the row is still there
    db_session.refresh(appointment)
    assert appointment.status == AppointmentStatus.CANCELLED


def test_cancelling_frees_the_slot_for_someone_else(user_client, service, appointment_factory):
    appointment = appointment_factory(at(10, 0))
    assert book(user_client, service, at(10, 0)).status_code == 409

    user_client.post(f"/appointments/{appointment.id}/cancel")
    assert book(user_client, service, at(10, 0)).status_code == 201


def test_cancelling_twice_is_rejected(user_client, appointment_factory):
    appointment = appointment_factory(at(10, 0), status=AppointmentStatus.CANCELLED)
    assert user_client.post(f"/appointments/{appointment.id}/cancel").status_code == 400


def test_cancelling_an_unknown_appointment_is_not_found(user_client):
    assert user_client.post("/appointments/99999/cancel").status_code == 404


# --- reschedule ---


def reschedule(client, appointment_id, start_time):
    return client.patch(
        f"/appointments/{appointment_id}/reschedule", json={"start_time": iso(start_time)}
    )


def test_rescheduling_moves_the_appointment(user_client, appointment_factory):
    appointment = appointment_factory(at(10, 0))
    response = reschedule(user_client, appointment.id, at(14, 0))

    assert response.status_code == 200
    body = response.json()
    assert parse(body["start_time"]) == at(14, 0)
    assert parse(body["end_time"]) == at(14, 30)


def test_rescheduling_onto_its_own_old_slot_is_allowed(user_client, appointment_factory):
    """Overlapping yourself is not a conflict - a 10 minute nudge keeps
    most of the old range, and must still go through."""
    appointment = appointment_factory(at(10, 0))
    assert reschedule(user_client, appointment.id, at(10, 10)).status_code == 200


def test_rescheduling_onto_another_appointment_conflicts(user_client, appointment_factory):
    appointment = appointment_factory(at(10, 0))
    appointment_factory(at(12, 0))
    assert reschedule(user_client, appointment.id, at(12, 15)).status_code == 409


def test_rescheduling_keeps_the_originally_booked_duration(
    user_client, service_factory, appointment_factory, db_session
):
    """The customer agreed to a 30 minute slot. If the service is later
    redefined as 60 minutes, their existing booking must not silently
    grow."""
    service = service_factory(duration_minutes=30)
    appointment = appointment_factory(at(10, 0), booked_service=service)

    service.duration_minutes = 60
    db_session.commit()

    response = reschedule(user_client, appointment.id, at(14, 0))
    assert response.status_code == 200
    assert parse(response.json()["end_time"]) == at(14, 30)


def test_rescheduling_into_the_past_is_rejected(user_client, appointment_factory):
    appointment = appointment_factory(at(10, 0))
    assert reschedule(user_client, appointment.id, past_at(10)).status_code == 400


def test_rescheduling_outside_working_hours_is_rejected(user_client, appointment_factory):
    appointment = appointment_factory(at(10, 0))
    assert reschedule(user_client, appointment.id, at(8, 0)).status_code == 400


def test_rescheduling_a_cancelled_appointment_is_rejected(user_client, appointment_factory):
    appointment = appointment_factory(at(10, 0), status=AppointmentStatus.CANCELLED)
    assert reschedule(user_client, appointment.id, at(14, 0)).status_code == 400
