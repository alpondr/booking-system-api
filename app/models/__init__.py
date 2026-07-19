# Import all models here so Base.metadata / Alembic sees every table.
from app.models.user import User  # noqa: F401
from app.models.service import Service  # noqa: F401
from app.models.appointment import Appointment  # noqa: F401
