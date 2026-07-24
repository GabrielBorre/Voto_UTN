import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / '.env')

user = os.getenv('POSTGRES_USER', 'postgres')
password = os.getenv('POSTGRES_PASSWORD', 'postgres')
host = os.getenv('POSTGRES_HOST', '127.0.0.1')
port = os.getenv('POSTGRES_PORT', '5432')
db_name = os.getenv('POSTGRES_DB', 'voto_utn')

conn = psycopg2.connect(dbname='postgres', user=user, password=password, host=host, port=port)
conn.autocommit = True
cur = conn.cursor()
cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
exists = cur.fetchone()
if exists:
    cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()", (db_name,))
    cur.execute(f'DROP DATABASE {db_name}')
cur.execute(f'CREATE DATABASE {db_name}')
print(f'CREATED {db_name}')
cur.close()
conn.close()
