"""Checks that the test infrastructure itself works, before any real
feature tests rely on it."""

from app.models.appointment import Appointment
from app.models.user import User
from tests.utils import at, iso


def test_health_check(client):
    response = client.get("/")
    assert response.status_code == 200


def test_fixtures_are_visible_through_the_api(user_client, service):
    """The API request and the test must share the same DB session -
    if they didn't, this service wouldn't exist yet from the API's side."""
    response = user_client.get("/services")
    assert response.status_code == 200
    assert [s["name"] for s in response.json()] == [service.name]


def test_authenticated_client_is_logged_in(user_client, user):
    response = user_client.get("/auth/me")
    assert response.status_code == 200
    assert response.json()["email"] == user.email


def test_anonymous_client_has_no_token(client):
    assert client.get("/auth/me").status_code == 401


# The next two tests write the same email. They only both pass if each
# test's writes get rolled back - i.e. proof that isolation works.
def test_isolation_first_write(db_session):
    db_session.add(User(email="isolation@example.com", hashed_password="x"))
    db_session.commit()
    assert db_session.query(User).filter_by(email="isolation@example.com").count() == 1


def test_isolation_second_write_sees_a_clean_db(db_session):
    assert db_session.query(User).filter_by(email="isolation@example.com").count() == 0
    db_session.add(User(email="isolation@example.com", hashed_password="x"))
    db_session.commit()


# Same idea, but through the application: create_appointment() calls
# db.commit() itself. That commit must land on a savepoint, not on the
# outer transaction, or every appointment test would leak into the next.
def test_isolation_covers_commits_made_by_app_code(user_client, service, db_session):
    response = user_client.post(
        "/appointments",
        json={"service_id": service.id, "start_time": iso(at(10, 0))},
    )
    assert response.status_code == 201, response.text
    assert db_session.query(Appointment).count() == 1


def test_app_code_commit_was_rolled_back(db_session):
    assert db_session.query(Appointment).count() == 0
