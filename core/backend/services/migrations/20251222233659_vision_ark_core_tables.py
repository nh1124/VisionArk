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
        """Apply migration"""
        # 1. Nodes table
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
        
        # 2. Chat Sessions table
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id VARCHAR(36) PRIMARY KEY,
                node_id VARCHAR(36) NOT NULL,
                parent_session_id VARCHAR(36),
                title VARCHAR(255),
                summary TEXT,
                is_archived BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP,
                CONSTRAINT fk_node FOREIGN KEY (node_id) REFERENCES nodes(id) ON DELETE CASCADE,
                CONSTRAINT fk_parent_session FOREIGN KEY (parent_session_id) REFERENCES chat_sessions(id) ON DELETE SET NULL
            )
        """))
        
        # 3. Chat Messages table
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id VARCHAR(36) PRIMARY KEY,
                session_id VARCHAR(36) NOT NULL,
                role VARCHAR(50) NOT NULL,
                content TEXT NOT NULL,
                meta_payload JSONB,
                is_excluded BOOLEAN DEFAULT FALSE,
                token_count INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_session FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
            )
        """))
        
        # 4. Uploaded Files table
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS uploaded_files (
                id VARCHAR(36) PRIMARY KEY,
                node_id VARCHAR(36) NOT NULL,
                filename VARCHAR(255) NOT NULL,
                storage_path VARCHAR(512) NOT NULL,
                mime_type VARCHAR(100) NOT NULL,
                size_bytes INTEGER NOT NULL,
                vector_status VARCHAR(50) DEFAULT 'PENDING',
                kc_sync_status VARCHAR(50) DEFAULT 'PENDING',
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_node_file FOREIGN KEY (node_id) REFERENCES nodes(id) ON DELETE CASCADE
            )
        """))
        
        # 5. File Chunks table
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS file_chunks (
                id SERIAL PRIMARY KEY,
                file_id VARCHAR(36) NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                metadata_json JSONB,
                CONSTRAINT fk_file FOREIGN KEY (file_id) REFERENCES uploaded_files(id) ON DELETE CASCADE
            )
        """))

    def down(self, session):
        """Revert migration"""
        session.execute(text("DROP TABLE IF EXISTS file_chunks"))
        session.execute(text("DROP TABLE IF EXISTS uploaded_files"))
        session.execute(text("DROP TABLE IF EXISTS chat_messages"))
        session.execute(text("DROP TABLE IF EXISTS chat_sessions"))
        session.execute(text("DROP TABLE IF EXISTS nodes"))
