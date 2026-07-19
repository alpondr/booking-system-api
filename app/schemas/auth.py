from pydantic import BaseModel


# Response of the /login endpoint
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# What we decode out of the JWT payload
class TokenPayload(BaseModel):
    sub: str | None = None  # "subject" claim, we store the user id here
