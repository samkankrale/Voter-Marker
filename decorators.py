from jose import jwt, JWTError, ExpiredSignatureError
from functools import wraps
from fastapi import Request, HTTPException

SECRET_KEY = "b21ef1d6b02ebea15bb36009af894fe107d0a5734617114cfbc792cd2f2177edbb86bbfcdc7d97daca782be343620b52b67f1749768902b1b8e770f058896b0d"
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
