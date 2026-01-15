from jose import jwt, JWTError, ExpiredSignatureError
from functools import wraps
from fastapi import Request, HTTPException

SECRET_KEY = "d499fc94c6f320d3bfef78671fa9e9b4bbb6c82b93eda7b45c70ee425501fd2d251353cf209a3d9e78f3712d9170aaf93d48ef1f51d2e6ad262ee2e81b958d44"
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
