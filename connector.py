import pymysql

def connector():
    return pymysql.connect(
        host="localhost",
        user="sam",
        password="Sam@130201",
        database="election"

    )
