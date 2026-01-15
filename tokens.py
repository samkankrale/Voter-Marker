from jose import jwt, JWTError
import datetime

SECRET_KEY = "d499fc94c6f320d3bfef78671fa9e9b4bbb6c82b93eda7b45c70ee425501fd2d251353cf209a3d9e78f3712d9170aaf93d48ef1f51d2e6ad262ee2e81b958d44"
ALGORITHM = "HS256"
def create_token(data : dict, expires_delta : int = 1000):
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=expires_delta)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
