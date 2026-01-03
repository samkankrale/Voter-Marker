from jose import jwt, JWTError, ExpiredSignatureError
from functools import wraps
from fastapi import Request, HTTPException

SECRET_KEY = "83d1e3dd64d5abfa80e74c57da340b333a8acf087ba66437abfac6482f5ec1ab64cff21100517b2cbf1f1f0bb23115d7f689710cc71e3d0db86a8a215fbb27cf"
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
