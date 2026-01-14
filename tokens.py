from jose import jwt, JWTError
import datetime

SECRET_KEY = "d2afc78c0a74354665e1f668a414af7f44a918c82f49184d39152d4221a2b130afa6a1e02488c0de2877c3295ff6872fdc8ac866f011d487fab67778bb0c0f39"
ALGORITHM = "HS256"
def create_token(data : dict, expires_delta : int = 1000):
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=expires_delta)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
