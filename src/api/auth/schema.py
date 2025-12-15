from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict


class Registraion(BaseModel):
    email: EmailStr = Field(description="Email of the user", default=None)
    password: str
    role: str = Field(default="user", description="Role of the user")
    confirm_password: str

    class config:
        orm_mode = True


class Login(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str

    class config:
        orm_mode = True
