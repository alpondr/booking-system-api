import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.database.base import Base
from app.database.session import get_db
from app.main import app

# Importing the models package registers every table on Base.metadata,
# which is what create_all() below builds the schema from.
from app.models import Service, User  # noqa: F401
from app.models.appointment import Appointment, AppointmentStatus
from app.models.user import UserRole
from app.services.appointment_service import calculate_end_time

TEST_PASSWORD = "testpassword123"


@pytest.fixture(scope="session")
def engine():
    """One engine (and one schema build) for the whole test session.

    Alembic is deliberately not used here: migrations are a separate
    concern, and tests should run against the schema the models declare.
    """
    url = settings.test_database_url
    if not url:
        pytest.exit("TEST_DATABASE_URL is not set. See .env.example.")
    # This fixture drops every table, so pointing it at the dev database
    # would wipe real data. Refuse loudly instead.
    if url == settings.database_url:
        pytest.exit("TEST_DATABASE_URL must be a different database than DATABASE_URL.")

    test_engine = create_engine(url)
    Base.metadata.drop_all(test_engine)
    Base.metadata.create_all(test_engine)
    yield test_engine
    Base.metadata.drop_all(test_engine)
    test_engine.dispose()


@pytest.fixture
def db_session(engine):
    """A session whose writes are rolled back after each test.

    The trick: open a connection, start a transaction on it by hand, and
    bind the session to that connection. join_transaction_mode="create_savepoint"
    makes the session's own commit() land on a SAVEPOINT instead of the
    outer transaction - so application code can call db.commit() freely
    and we can still undo everything at the end.

    Cheaper and safer than recreating tables between tests, and it means
    tests can't leak state into each other.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session):
    """Anonymous API client wired to the test session.

    dependency_overrides swaps out get_db so the endpoints use the same
    rolled-back session the test does - otherwise the request would open
    its own connection and never see the test's fixtures.
    """
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _create_user(db_session, email: str, role: UserRole) -> User:
    user = User(email=email, hashed_password=hash_password(TEST_PASSWORD), role=role)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _authenticated_client(email: str) -> TestClient:
    """A second TestClient carrying this user's token.

    Separate instance per user on purpose: setting headers on the shared
    `client` would leak auth into tests that expect to be anonymous.
    """
    test_client = TestClient(app)
    response = test_client.post(
        "/auth/login", data={"username": email, "password": TEST_PASSWORD}
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    test_client.headers["Authorization"] = f"Bearer {token}"
    return test_client


@pytest.fixture
def user(db_session) -> User:
    return _create_user(db_session, "user@example.com", UserRole.USER)


@pytest.fixture
def other_user(db_session) -> User:
    """Second regular user, for ownership tests."""
    return _create_user(db_session, "other@example.com", UserRole.USER)


@pytest.fixture
def admin(db_session) -> User:
    # Created directly in the DB because the API intentionally offers no
    # way to register an admin.
    return _create_user(db_session, "admin@example.com", UserRole.ADMIN)


@pytest.fixture
def user_client(client, user) -> TestClient:
    return _authenticated_client(user.email)


@pytest.fixture
def other_user_client(client, other_user) -> TestClient:
    return _authenticated_client(other_user.email)


@pytest.fixture
def admin_client(client, admin) -> TestClient:
    return _authenticated_client(admin.email)


@pytest.fixture
def service_factory(db_session):
    """Creates services with a chosen duration, since slot/overlap tests
    care about how long an appointment actually is."""

    def _factory(name: str = "Hair Cut", duration_minutes: int = 30) -> Service:
        service = Service(name=name, duration_minutes=duration_minutes)
        db_session.add(service)
        db_session.commit()
        db_session.refresh(service)
        return service

    return _factory


@pytest.fixture
def service(service_factory) -> Service:
    """Default 30-minute service."""
    return service_factory()


@pytest.fixture
def appointment_factory(db_session, user, service):
    """Writes an appointment straight to the DB.

    Overlap tests need appointments to already exist, including ones the
    API would refuse to create (cancelled, in the past). Going through
    POST /appointments for setup would make those cases impossible.
    """

    def _factory(
        start_time,
        end_time=None,
        status: AppointmentStatus = AppointmentStatus.ACTIVE,
        owner: User | None = None,
        booked_service: Service | None = None,
    ) -> Appointment:
        booked_service = booked_service or service
        appointment = Appointment(
            user_id=(owner or user).id,
            service_id=booked_service.id,
            start_time=start_time,
            end_time=end_time or calculate_end_time(start_time, booked_service),
            status=status,
        )
        db_session.add(appointment)
        db_session.commit()
        db_session.refresh(appointment)
        return appointment

    return _factory
