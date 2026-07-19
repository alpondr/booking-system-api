from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from app.database.base import Base


class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)  # e.g. "Hair Cut"
    duration_minutes = Column(Integer, nullable=False)  # e.g. 30

    appointments = relationship("Appointment", back_populates="service")
