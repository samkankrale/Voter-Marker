from jose import jwt, JWTError, ExpiredSignatureError
from functools import wraps
from fastapi import Request, HTTPException

SECRET_KEY = "0b2ac2f10b85deddeb11ccc1e80d0e3e8331219db2181d56e4265a6e5832348c6861e66bbd53f36e1a0ce9a9dc9bde0a519ad50247744739c0f90ced2015a97a"
ALGORITHM = "HS256"

def jwt_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        request: Request = kwargs.get("request")
        if not request:
            raise HTTPException(status_code=400, detail="Request object missing")

        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not token:
            raise HTTPException(status_code=401, detail="Token missing")

        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        except ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except JWTError:
            raise HTTPException(status_code=401, detail="Invalid token")

        kwargs["id"] = str(payload.get("id"))
        return func(*args, **kwargs)
    return wrapper
