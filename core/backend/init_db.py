from models.database import init_database, get_engine
import os

def run_init():
    db_url = os.getenv("DATABASE_URL")
    print(f"Initializing database at {db_url}...")
    try:
        engine = init_database(db_url)
        print("Database initialized successfully (Base.metadata.create_all).")
    except Exception as e:
        print(f"Error initializing database: {e}")

if __name__ == "__main__":
    run_init()
