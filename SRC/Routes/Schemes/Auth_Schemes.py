from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: str
    password: str


class ApiKeyGenerateResponse(BaseModel):
    api_key: str
    message: str


class ApiKeyStatusResponse(BaseModel):
    has_key: bool
