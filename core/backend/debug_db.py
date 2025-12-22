from sqlalchemy import text
from models.database import get_engine, get_session

def test_sql():
    engine = get_engine()
    session = get_session(engine)
    try:
        print("Testing Nodes table creation...")
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS nodes (
                id VARCHAR(36) PRIMARY KEY,
                user_id VARCHAR(36) NOT NULL,
                name VARCHAR(100) NOT NULL,
                display_name VARCHAR(200) NOT NULL,
                node_type VARCHAR(50) NOT NULL,
                lbs_access_level VARCHAR(50) DEFAULT 'READ_ONLY',
                is_archived BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP,
                CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """))
        session.commit()
        print("Success!")
    except Exception as e:
        print(f"Error: {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    test_sql()
