"""Who is allowed to do what.

Two separate ideas get tested here, and they fail in different ways:

- role checks (require_admin): a regular user must not reach admin-only
  endpoints at all.
- ownership checks: a logged-in user may only touch their own
  appointments, even though the endpoint itself is open to everyone.

The second one is the easier one to get wrong, because the request looks
perfectly legitimate - valid token, existing appointment id.
"""

from app.models.appointment import AppointmentStatus
from tests.utils import at, iso


# --- admin-only service management ---


def test_anonymous_cannot_create_a_service(client):
    response = client.post("/services", json={"name": "Hair Cut", "duration_minutes": 30})
    assert response.status_code == 401


def test_regular_user_cannot_create_a_service(user_client):
    response = user_client.post("/services", json={"name": "Hair Cut", "duration_minutes": 30})
    assert response.status_code == 403


def test_admin_can_create_a_service(admin_client):
    response = admin_client.post("/services", json={"name": "Hair Cut", "duration_minutes": 30})
    assert response.status_code == 201
    assert response.json()["duration_minutes"] == 30


def test_regular_user_cannot_update_a_service(user_client, service):
    assert user_client.patch(f"/services/{service.id}", json={"name": "New"}).status_code == 403


def test_admin_can_update_a_service(admin_client, service):
    response = admin_client.patch(f"/services/{service.id}", json={"name": "New"})
    assert response.status_code == 200
    assert response.json()["name"] == "New"
    # PATCH is partial: an unsent field keeps its old value
    assert response.json()["duration_minutes"] == service.duration_minutes


def test_regular_user_cannot_delete_a_service(user_client, service):
    assert user_client.delete(f"/services/{service.id}").status_code == 403


def test_admin_can_delete_an_unused_service(admin_client, service):
    assert admin_client.delete(f"/services/{service.id}").status_code == 204


def test_deleting_a_service_with_appointments_conflicts(admin_client, service, appointment_factory):
    """The foreign key protects appointment history - a deleted service
    would orphan rows that record something that actually happened."""
    appointment_factory(at(10, 0))
    assert admin_client.delete(f"/services/{service.id}").status_code == 409


def test_updating_an_unknown_service_is_not_found(admin_client, service):
    assert admin_client.patch(f"/services/{service.id + 999}", json={"name": "x"}).status_code == 404


def test_reading_services_is_open_to_everyone(client, service):
    """Browsing has to work before signing up, so these stay public."""
    assert client.get("/services").status_code == 200
    assert client.get(f"/services/{service.id}").status_code == 200


# --- admin-only appointment listing ---


def test_anonymous_cannot_list_all_appointments(client):
    assert client.get("/appointments").status_code == 401


def test_regular_user_cannot_list_all_appointments(user_client):
    assert user_client.get("/appointments").status_code == 403


def test_admin_sees_appointments_from_every_user(
    admin_client, appointment_factory, user, other_user
):
    appointment_factory(at(10, 0), owner=user)
    appointment_factory(at(12, 0), owner=other_user)

    response = admin_client.get("/appointments")
    assert response.status_code == 200
    owners = {item["user_id"] for item in response.json()["items"]}
    assert owners == {user.id, other_user.id}


# --- ownership ---


def test_a_user_cannot_cancel_someone_elses_appointment(
    other_user_client, appointment_factory, user
):
    """Valid token, real appointment id, wrong owner - the only thing
    standing between the two accounts is this check."""
    appointment = appointment_factory(at(10, 0), owner=user)
    assert other_user_client.post(f"/appointments/{appointment.id}/cancel").status_code == 403


def test_a_user_cannot_reschedule_someone_elses_appointment(
    other_user_client, appointment_factory, user
):
    appointment = appointment_factory(at(10, 0), owner=user)
    response = other_user_client.patch(
        f"/appointments/{appointment.id}/reschedule", json={"start_time": iso(at(14, 0))}
    )
    assert response.status_code == 403


def test_a_refused_cancel_leaves_the_appointment_untouched(
    other_user_client, appointment_factory, user, db_session
):
    appointment = appointment_factory(at(10, 0), owner=user)
    other_user_client.post(f"/appointments/{appointment.id}/cancel")

    db_session.refresh(appointment)
    assert appointment.status == AppointmentStatus.ACTIVE


def test_admins_are_not_exempt_from_the_ownership_check(admin_client, appointment_factory, user):
    """Admins can *see* every appointment, but cancelling still goes
    through the owner-only endpoint. Worth pinning down so the two rules
    don't get quietly merged later."""
    appointment = appointment_factory(at(10, 0), owner=user)
    assert admin_client.post(f"/appointments/{appointment.id}/cancel").status_code == 403
