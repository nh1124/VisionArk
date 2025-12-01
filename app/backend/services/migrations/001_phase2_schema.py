"""
Initial migration: Add Phase 2 schema enhancements
"""
from sqlalchemy import text
from ..migrate import Migration


class Migration001(Migration):
    version = "001"
    description = "Add estimated_hours and RAG metadata columns"
    
    def up(self, session):
        """Apply migration"""
        # Add estimated_hours to tasks table
        try:
            session.execute(text("""
                ALTER TABLE tasks ADD COLUMN estimated_hours FLOAT
            """))
        except Exception:
            pass  # Column might already exist
        
        # Add RAG tracking columns
        try:
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS rag_metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    spoke_name TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_hash TEXT,
                    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    chunk_count INTEGER DEFAULT 0,
                    UNIQUE(spoke_name, file_path)
                )
            """))
        except Exception:
            pass
        
        # Add context rotation tracking
        try:
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS archived_contexts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    spoke_name TEXT NOT NULL,
                    archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    summary_path TEXT,
                    log_path TEXT,
                    token_count INTEGER
                )
            """))
        except Exception:
            pass
    
    def down(self, session):
        """Revert migration"""
        # Remove columns (SQLite doesn't support DROP COLUMN easily, so we skip)
        # In production, would recreate table without the column
        pass
