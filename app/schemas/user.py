from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.user import UserRole


class UserBase(BaseModel):
    email: EmailStr


# What the client sends to register. Plain password here, it gets
# hashed before it's ever stored (see core/security.py in step 6).
class UserCreate(UserBase):
    password: str


# What we send back to the client. No password field on purpose.
class UserOut(UserBase):
    id: int
    role: UserRole

    # Lets pydantic build this schema straight from a SQLAlchemy model
    # instance (e.g. UserOut.model_validate(db_user)), not just from a dict.
    model_config = ConfigDict(from_attributes=True)
