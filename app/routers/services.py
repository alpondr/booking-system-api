from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.database.session import get_db
from app.models.service import Service
from app.schemas.service import ServiceCreate, ServiceOut, ServiceUpdate

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
