from pydantic import BaseModel

class Login(BaseModel):
    username: str
    password: str

class Users(BaseModel):
    name: str
    user_name: str
    password: str

class PasswordUpdate(BaseModel):
    password: str

class VisitWithNote(BaseModel):
    notes: str = ""