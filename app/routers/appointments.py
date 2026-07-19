from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database.session import get_db
from app.models.service import Service
from app.models.user import User
from app.schemas.appointment import AppointmentCreate, AppointmentOut
from app.services.appointment_service import (
    AppointmentInPastError,
    AppointmentOverlapError,
    OutsideWorkingHoursError,
    create_appointment,
)

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.post("", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
def book_appointment(
    appointment_in: AppointmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = db.get(Service, appointment_in.service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")

    # The service module knows nothing about HTTP - it raises plain
    # exceptions, and we translate each one to the right status code here.
    try:
        appointment = create_appointment(
            db=db,
            user_id=current_user.id,
            service=service,
            start_time=appointment_in.start_time,
        )
    except AppointmentInPastError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except OutsideWorkingHoursError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except AppointmentOverlapError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    return appointment
