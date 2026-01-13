from jose import jwt, JWTError
import datetime

SECRET_KEY = "83d1e3dd64d5abfa80e74c57da340b333a8acf087ba66437abfac6482f5ec1ab64cff21100517b2cbf1f1f0bb23115d7f689710cc71e3d0db86a8a215fbb27cf"
ALGORITHM = "HS256"
def create_token(data : dict, expires_delta : int = 1000):
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=expires_delta)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
