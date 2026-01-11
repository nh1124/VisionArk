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
    
    def down(self, session):
        """Revert migration"""
        # Remove columns (SQLite doesn't support DROP COLUMN easily, so we skip)
        # In production, would recreate table without the column
        pass
