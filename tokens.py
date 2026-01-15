from jose import jwt, JWTError
import datetime

SECRET_KEY = "b21ef1d6b02ebea15bb36009af894fe107d0a5734617114cfbc792cd2f2177edbb86bbfcdc7d97daca782be343620b52b67f1749768902b1b8e770f058896b0d"
ALGORITHM = "HS256"
def create_token(data : dict, expires_delta : int = 1000):
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=expires_delta)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
