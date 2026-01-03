import pymysql

def connector():
    return pymysql.connect(
        host="localhost",
        user="root",
        password="Sam@130201",
        database="election"
    )