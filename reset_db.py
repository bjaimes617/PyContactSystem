import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
database_url = os.getenv('DATABASE_URL')

try:
    # Disable SSL requirement strictly for the script connection if needed, but Supabase requires it.
    conn = psycopg2.connect(database_url, sslmode='require')
    conn.autocommit = True
    cursor = conn.cursor()
    
    print("Dropping schema public...")
    cursor.execute("DROP SCHEMA public CASCADE;")
    
    print("Recreating schema public...")
    cursor.execute("CREATE SCHEMA public;")
    
    print("Granting permissions...")
    cursor.execute("GRANT ALL ON SCHEMA public TO postgres;")
    cursor.execute("GRANT ALL ON SCHEMA public TO public;")
    
    cursor.close()
    conn.close()
    print("Database reset successfully.")
except Exception as e:
    print("Error resetting database:", str(e))
