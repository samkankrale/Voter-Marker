from jose import jwt, JWTError
import datetime

SECRET_KEY = "0b2ac2f10b85deddeb11ccc1e80d0e3e8331219db2181d56e4265a6e5832348c6861e66bbd53f36e1a0ce9a9dc9bde0a519ad50247744739c0f90ced2015a97a"
ALGORITHM = "HS256"
def create_token(data : dict, expires_delta : int = 1000):
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=expires_delta)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
