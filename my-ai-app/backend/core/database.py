import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv
import os

load_dotenv()


class DatabaseUnavailable(RuntimeError):
    """A required persistence operation could not complete."""


def get_db_connection():
    try:
        connection = mysql.connector.connect(
            host=os.getenv('DB_HOST'),
            port=int(os.getenv('DB_PORT')),
            database=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            connection_timeout=3,
            read_timeout=5,
            write_timeout=5,
        )
        return connection
    except Error as e:
        print(f"Lỗi kết nối MySQL: {e}")
        return None


def check_db_connection() -> bool:
    connection = get_db_connection()
    if not connection:
        return False

    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        return True
    except Error as e:
        print(f"Lỗi health check MySQL: {e}")
        return False
    finally:
        if cursor is not None:
            cursor.close()
        if connection.is_connected():
            connection.close()
