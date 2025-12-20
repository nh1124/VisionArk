"""
Database migration script to add user_id column to inbox_queue table.
Run this script once to migrate existing database.
"""
from sqlalchemy import create_engine, text
import os

def run_migration():
    """Add user_id column to inbox_queue if it doesn't exist."""
    
    # Get database URL from environment
    database_url = os.getenv(
        "DATABASE_URL", 
        "postgresql://atmos:atmos_dev_password@localhost:5432/atmos_db"
    )
    
    engine = create_engine(database_url)
    
    with engine.connect() as conn:
        # Check if column exists
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'inbox_queue' AND column_name = 'user_id'
        """))
        
        if result.fetchone() is None:
            print("Adding user_id column to inbox_queue...")
            conn.execute(text("""
                ALTER TABLE inbox_queue 
                ADD COLUMN user_id VARCHAR(36)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_inbox_queue_user_id 
                ON inbox_queue (user_id)
            """))
            conn.commit()
            print("✅ Migration complete: user_id column added")
        else:
            print("✅ user_id column already exists")


if __name__ == "__main__":
    run_migration()
