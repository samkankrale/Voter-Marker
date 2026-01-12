from pymysql import connect
from pymysql.cursors import DictCursor
import threading
from typing import Optional
from contextlib import contextmanager

class ConnectionPool:
    """Manages database connections with pooling"""
    
    def __init__(self, max_connections: int = 10):
        self._pool = []
        self._used = {}
        self._lock = threading.Lock()
        self._max_connections = max_connections
        self._db_config = None
        
    def initialize(self, host: str, user: str, password: str, database: str, **kwargs):
        """Initialize pool with database configuration"""
        self._db_config = {
            'host': host,
            'user': user,
            'password': password,
            'database': database,
            **kwargs
        }
    
    def _create_connection(self):
        """Create a new database connection"""
        if not self._db_config:
            raise RuntimeError("Connection pool not initialized")
        return connect(**self._db_config)
    
    def get_connection(self):
        """Get a connection from the pool"""
        with self._lock:
            # Try to get from pool
            if self._pool:
                conn = self._pool.pop()
                try:
                    conn.ping(reconnect=True)
                    return conn
                except:
                    pass
            
            # Create new if under limit
            if len(self._used) < self._max_connections:
                return self._create_connection()
            
            # Wait and retry if at limit
            raise RuntimeError("Connection pool exhausted")
    
    def return_connection(self, conn):
        """Return a connection to the pool"""
        with self._lock:
            try:
                conn.ping(reconnect=True)
                if len(self._pool) < self._max_connections:
                    self._pool.append(conn)
                else:
                    conn.close()
            except:
                try:
                    conn.close()
                except:
                    pass
    
    def close_all(self):
        """Close all connections in pool"""
        with self._lock:
            for conn in self._pool:
                try:
                    conn.close()
                except:
                    pass
            self._pool.clear()
            
            for conn in self._used.values():
                try:
                    conn.close()
                except:
                    pass
            self._used.clear()

# Global connection pool instance
connection_pool = ConnectionPool(max_connections=20)

@contextmanager
def get_db_connection():
    """Context manager for getting database connections"""
    conn = connection_pool.get_connection()
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        connection_pool.return_connection(conn)

def get_cursor(connection, dict_cursor: bool = True):
    """Get a cursor from connection"""
    if dict_cursor:
        return connection.cursor(DictCursor)
    return connection.cursor()