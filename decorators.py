from jose import jwt, JWTError, ExpiredSignatureError
from functools import wraps
from fastapi import Request, HTTPException

SECRET_KEY = "d2afc78c0a74354665e1f668a414af7f44a918c82f49184d39152d4221a2b130afa6a1e02488c0de2877c3295ff6872fdc8ac866f011d487fab67778bb0c0f39"
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
