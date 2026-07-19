from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.database.session import get_db
from app.models.service import Service
from app.schemas.appointment import AvailableSlot
from app.schemas.service import ServiceCreate, ServiceOut, ServiceUpdate
from app.services.appointment_service import BUSINESS_TIMEZONE, find_available_slots

router = APIRouter(prefix="/services", tags=["services"])


# Reading services is open to any logged-in user (or even anonymous) -
# they need to browse services before they can book one. Only
# create/update/delete are admin-only.
@router.get("", response_model=list[ServiceOut])
def list_services(db: Session = Depends(get_db)):
    return db.query(Service).order_by(Service.id).all()


@router.get("/{service_id}", response_model=ServiceOut)
def get_service(service_id: int, db: Session = Depends(get_db)):
    service = db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    return service


@router.get("/{service_id}/available-slots", response_model=list[AvailableSlot])
def get_available_slots(
    service_id: int,
    slot_date: date = Query(..., alias="date"),
    db: Session = Depends(get_db),
):
    service = db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")

    today_local = datetime.now(BUSINESS_TIMEZONE).date()
    if slot_date < today_local:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot list available slots for a past date",
        )

    slots = find_available_slots(db, service, slot_date)
    return [AvailableSlot(start_time=start, end_time=end) for start, end in slots]


@router.post("", response_model=ServiceOut, status_code=status.HTTP_201_CREATED)
def create_service(
    service_in: ServiceCreate,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    service = Service(**service_in.model_dump())
    db.add(service)
    db.commit()
    db.refresh(service)
    return service


@router.patch("/{service_id}", response_model=ServiceOut)
def update_service(
    service_id: int,
    service_in: ServiceUpdate,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    service = db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")

    # exclude_unset -> only fields the client actually sent get overwritten
    for field, value in service_in.model_dump(exclude_unset=True).items():
        setattr(service, field, value)

    db.commit()
    db.refresh(service)
    return service


@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_service(
    service_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    service = db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")

    try:
        db.delete(service)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete a service that has existing appointments",
        )
