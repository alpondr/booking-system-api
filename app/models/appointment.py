import enum

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer
from sqlalchemy.orm import relationship

from app.database.base import Base


class AppointmentStatus(str, enum.Enum):
    ACTIVE = "active"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)

    # timezone=True -> Postgres stores these as TIMESTAMPTZ (always UTC
    # internally). We always work with UTC datetimes in the app code.
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)

    status = Column(Enum(AppointmentStatus), nullable=False, default=AppointmentStatus.ACTIVE)

    user = relationship("User", back_populates="appointments")
    service = relationship("Service", back_populates="appointments")
