from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database.session import get_db
from app.models.appointment import Appointment
from app.models.service import Service
from app.models.user import User
from app.schemas.appointment import AppointmentCreate, AppointmentOut, AppointmentReschedule
from app.services.appointment_service import (
    AppointmentInPastError,
    AppointmentNotActiveError,
    AppointmentOverlapError,
    OutsideWorkingHoursError,
    cancel_appointment,
    create_appointment,
    reschedule_appointment,
)

router = APIRouter(prefix="/appointments", tags=["appointments"])


def _get_owned_appointment(db: Session, appointment_id: int, current_user: User) -> Appointment:
    appointment = db.get(Appointment, appointment_id)
    if appointment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    if appointment.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only manage your own appointments",
        )
    return appointment


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


@router.post("/{appointment_id}/cancel", response_model=AppointmentOut)
def cancel(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    appointment = _get_owned_appointment(db, appointment_id, current_user)
    try:
        return cancel_appointment(db, appointment)
    except AppointmentNotActiveError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.patch("/{appointment_id}/reschedule", response_model=AppointmentOut)
def reschedule(
    appointment_id: int,
    reschedule_in: AppointmentReschedule,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    appointment = _get_owned_appointment(db, appointment_id, current_user)
    try:
        return reschedule_appointment(db, appointment, reschedule_in.start_time)
    except AppointmentNotActiveError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except AppointmentInPastError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except OutsideWorkingHoursError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except AppointmentOverlapError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
