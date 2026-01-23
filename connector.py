from pymysql import connect
from pymysql.cursors import DictCursor
import threading
from contextlib import contextmanager

class ConnectionPool:
    """Simple connection pool - works like your original but with basic improvements"""
    
    def __init__(self, max_connections: int = 50):
        self._pool = []
        self._lock = threading.Lock()
        self._max_connections = max_connections
        self._db_config = None
        self._active_count = 0
        
    def initialize(self, host: str, user: str, password: str, database: str, **kwargs):
        """Initialize pool with database configuration"""
        self._db_config = {
            'host': host,
            'user': user,
            'password': password,
            'database': database,
            **kwargs
        }
        print(f"✅ Database pool initialized (max connections: {self._max_connections})")
    
    def _create_connection(self):
        """Create a new database connection"""
        if not self._db_config:
            raise RuntimeError("Connection pool not initialized")
        return connect(**self._db_config)
    
    def get_connection(self, timeout=10):
        """Get a connection from the pool with retry logic"""
        import time
        start_time = time.time()
        
        while True:
            with self._lock:
                # Try to get from pool
                if self._pool:
                    conn = self._pool.pop()
                    try:
                        conn.ping(reconnect=True)
                        self._active_count += 1
                        return conn
                    except:
                        # Connection dead, create new one
                        pass
                
                # Create new connection if under limit
                if self._active_count < self._max_connections:
                    conn = self._create_connection()
                    self._active_count += 1
                    return conn
            
            # Pool exhausted - check timeout
            elapsed = time.time() - start_time
            if elapsed >= timeout:
                raise RuntimeError(
                    f"Connection pool timeout after {timeout}s. "
                    f"All {self._max_connections} connections in use. "
                    f"Try again later or increase pool size."
                )
            
            # Wait a bit and retry
            print(f"⚠️ Pool busy ({self._active_count}/{self._max_connections}), waiting... ({elapsed:.1f}s)")
            time.sleep(0.1)  # Wait 100ms before retry
    
    def return_connection(self, conn):
        """Return a connection to the pool"""
        if conn is None:
            return
            
        with self._lock:
            self._active_count -= 1
            
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
            self._active_count = 0
        print("✅ All database connections closed")


# Global connection pool instance
connection_pool = ConnectionPool(max_connections=50)


@contextmanager
def get_db_connection():
    """Context manager for getting database connections"""
    conn = None
    try:
        conn = connection_pool.get_connection()
        yield conn
        conn.commit()
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except:
                pass
        raise e
    finally:
        if conn:
            connection_pool.return_connection(conn)


def get_cursor(connection, dict_cursor: bool = True):
    """Get a cursor from connection"""
    if dict_cursor:
        return connection.cursor(DictCursor)
    return connection.cursor()