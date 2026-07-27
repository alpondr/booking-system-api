"""Listing endpoints: filtering and pagination.

GET /appointments/me and GET /appointments look similar but answer
different questions - "mine" versus "everyone's" - so the filters are
tested separately on each.
"""

from datetime import timedelta

from app.models.appointment import AppointmentStatus
from tests.utils import at, local_today, past_at

# --- GET /appointments/me ---


def test_my_list_only_contains_my_appointments(user_client, appointment_factory, user, other_user):
    appointment_factory(at(10, 0), owner=user)
    appointment_factory(at(12, 0), owner=other_user)

    body = user_client.get("/appointments/me").json()
    assert body["total"] == 1
    assert body["items"][0]["user_id"] == user.id


def test_my_list_includes_cancelled_appointments(user_client, appointment_factory):
    appointment_factory(at(10, 0), status=AppointmentStatus.CANCELLED)
    body = user_client.get("/appointments/me").json()

    # Soft-deleted rows still belong in your own history
    assert body["total"] == 1
    assert body["items"][0]["status"] == AppointmentStatus.CANCELLED.value


def test_upcoming_filter_excludes_past_appointments(user_client, appointment_factory):
    appointment_factory(at(10, 0))
    appointment_factory(past_at(10))

    body = user_client.get("/appointments/me", params={"time_filter": "upcoming"}).json()
    assert body["total"] == 1


def test_past_filter_excludes_upcoming_appointments(user_client, appointment_factory):
    appointment_factory(at(10, 0))
    appointment_factory(past_at(10))

    body = user_client.get("/appointments/me", params={"time_filter": "past"}).json()
    assert body["total"] == 1


def test_no_filter_returns_both(user_client, appointment_factory):
    appointment_factory(at(10, 0))
    appointment_factory(past_at(10))

    assert user_client.get("/appointments/me").json()["total"] == 2


def test_an_unknown_time_filter_is_rejected(user_client):
    response = user_client.get("/appointments/me", params={"time_filter": "yesterday"})
    assert response.status_code == 422


def test_my_list_requires_authentication(client):
    assert client.get("/appointments/me").status_code == 401


# --- pagination ---


def test_pages_split_the_results_and_keep_the_total(user_client, appointment_factory):
    for hour in range(9, 14):
        appointment_factory(at(hour, 0))

    first = user_client.get("/appointments/me", params={"page": 1, "page_size": 2}).json()
    second = user_client.get("/appointments/me", params={"page": 2, "page_size": 2}).json()

    # total is the size of the whole result set, not of the page
    assert first["total"] == second["total"] == 5
    assert len(first["items"]) == len(second["items"]) == 2
    assert {i["id"] for i in first["items"]}.isdisjoint({i["id"] for i in second["items"]})


def test_results_are_ordered_by_start_time(user_client, appointment_factory):
    appointment_factory(at(14, 0))
    appointment_factory(at(9, 0))
    appointment_factory(at(11, 0))

    items = user_client.get("/appointments/me").json()["items"]
    assert [i["start_time"] for i in items] == sorted(i["start_time"] for i in items)


def test_a_page_past_the_end_is_empty_but_valid(user_client, appointment_factory):
    appointment_factory(at(10, 0))
    body = user_client.get("/appointments/me", params={"page": 5}).json()

    assert body["items"] == []
    assert body["total"] == 1


def test_page_numbers_start_at_one(user_client):
    assert user_client.get("/appointments/me", params={"page": 0}).status_code == 422


def test_page_size_is_capped(user_client):
    """Without an upper bound, one request could ask for the entire table."""
    assert user_client.get("/appointments/me", params={"page_size": 1000}).status_code == 422


# --- GET /appointments (admin filters) ---


def test_admin_can_filter_by_status(admin_client, appointment_factory):
    appointment_factory(at(10, 0))
    appointment_factory(at(12, 0), status=AppointmentStatus.CANCELLED)

    body = admin_client.get("/appointments", params={"status": "cancelled"}).json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == AppointmentStatus.CANCELLED.value


def test_admin_can_filter_from_a_date(admin_client, appointment_factory):
    appointment_factory(at(10, 0, days_ahead=1))
    appointment_factory(at(10, 0, days_ahead=3))

    date_from = (local_today() + timedelta(days=2)).isoformat()
    assert admin_client.get("/appointments", params={"date_from": date_from}).json()["total"] == 1


def test_admin_can_filter_up_to_a_date(admin_client, appointment_factory):
    appointment_factory(at(10, 0, days_ahead=1))
    appointment_factory(at(10, 0, days_ahead=3))

    date_to = (local_today() + timedelta(days=2)).isoformat()
    assert admin_client.get("/appointments", params={"date_to": date_to}).json()["total"] == 1


def test_date_filters_are_inclusive_of_the_whole_local_day(admin_client, appointment_factory):
    """date_to=<day> has to cover that entire day in business local time,
    not stop at 00:00 UTC - otherwise a late-evening appointment silently
    falls outside its own date."""
    appointment_factory(at(17, 30, days_ahead=1))

    day = (local_today() + timedelta(days=1)).isoformat()
    body = admin_client.get("/appointments", params={"date_from": day, "date_to": day}).json()
    assert body["total"] == 1
