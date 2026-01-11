"""
Migration 20251222233659: Vision Ark Core Tables
Created: 2025-12-22T23:36:59.963560
"""
from sqlalchemy import text
from services.migrate import Migration


class Migration20251222233659(Migration):
    version = "20251222233659"
    description = "Vision Ark Core Tables"
    
    def up(self, session):
        """Apply migration - Core tables now handled by models.database.Base.metadata.create_all"""
        # Tables nodes, chat_sessions, chat_messages, uploaded_files, file_chunks 
        # are already created by the ORM initialization in database.py.
        pass

    def down(self, session):
        """Revert migration"""
        session.execute(text("DROP TABLE IF EXISTS file_chunks"))
        session.execute(text("DROP TABLE IF EXISTS uploaded_files"))
        session.execute(text("DROP TABLE IF EXISTS chat_messages"))
        session.execute(text("DROP TABLE IF EXISTS chat_sessions"))
        session.execute(text("DROP TABLE IF EXISTS nodes"))
