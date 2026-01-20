"""
Migration Script: Create Project Table and Reorganize Schema
This script handles the V6 database migration:
1. Creates the 'projects' table
2. Migrates data from 'nodes' to 'projects'
3. Adds new columns to 'nodes' (project_id, parent_node_id, node_type, etc.)
4. Migrates 'agent_profiles' data into 'nodes'
5. Updates 'chat_sessions' and 'uploaded_files' to use project_id
"""
import os
import sys
from uuid import uuid4
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def run_migration():
    """Run the V6 migration."""
    from sqlalchemy import create_engine, text, inspect
    
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ DATABASE_URL not set.")
        sys.exit(1)
    
    # Convert async URL to sync
    if database_url.startswith("postgresql+asyncpg://"):
        database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    
    print(f"🔗 Connecting to database...")
    engine = create_engine(database_url)
    
    with engine.connect() as conn:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        # Step 1: Create projects table if not exists
        if "projects" not in tables:
            print("🔄 Step 1: Creating 'projects' table...")
            conn.execute(text("""
                CREATE TABLE projects (
                    id VARCHAR(36) PRIMARY KEY,
                    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
                    name VARCHAR(200) NOT NULL,
                    strategy_id VARCHAR(36),
                    status VARCHAR(20) DEFAULT 'active',
                    priority INTEGER DEFAULT 3,
                    review_cadence VARCHAR(50),
                    lbs_access_level VARCHAR(50) DEFAULT 'READ_ONLY',
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX ix_projects_user_id ON projects (user_id)"))
            conn.execute(text("CREATE INDEX ix_projects_name ON projects (name)"))
            conn.commit()
            print("   ✓ 'projects' table created")
        else:
            print("   ⏭ 'projects' table already exists")
        
        # Step 2: Check if nodes table has old structure (user_id column)
        node_columns = [col["name"] for col in inspector.get_columns("nodes")]
        
        if "user_id" in node_columns and "project_id" not in node_columns:
            print("🔄 Step 2: Migrating nodes → projects...")
            
            # Create projects from existing nodes
            conn.execute(text("""
                INSERT INTO projects (id, user_id, name, lbs_access_level, created_at, updated_at)
                SELECT id, user_id, display_name, COALESCE(lbs_access_level, 'READ_ONLY'), 
                       created_at, COALESCE(updated_at, created_at)
                FROM nodes
                WHERE id NOT IN (SELECT id FROM projects)
            """))
            conn.commit()
            print("   ✓ Projects created from nodes")
            
            # Add new columns to nodes
            print("🔄 Step 3: Adding new columns to 'nodes'...")
            try:
                conn.execute(text("ALTER TABLE nodes ADD COLUMN project_id VARCHAR(36) REFERENCES projects(id)"))
                conn.commit()
            except Exception as e:
                if "already exists" not in str(e).lower():
                    print(f"   ⚠ project_id: {e}")
            
            try:
                conn.execute(text("ALTER TABLE nodes ADD COLUMN parent_node_id VARCHAR(36) REFERENCES nodes(id)"))
                conn.commit()
            except Exception as e:
                if "already exists" not in str(e).lower():
                    print(f"   ⚠ parent_node_id: {e}")
            
            try:
                conn.execute(text("ALTER TABLE nodes ADD COLUMN node_type VARCHAR(20) DEFAULT 'PROJECT'"))
                conn.commit()
            except Exception as e:
                if "already exists" not in str(e).lower():
                    print(f"   ⚠ node_type: {e}")
            
            try:
                conn.execute(text("ALTER TABLE nodes ADD COLUMN role_name VARCHAR(50)"))
                conn.commit()
            except Exception as e:
                if "already exists" not in str(e).lower():
                    print(f"   ⚠ role_name: {e}")
            
            try:
                conn.execute(text("ALTER TABLE nodes ADD COLUMN system_prompt TEXT"))
                conn.commit()
            except Exception as e:
                if "already exists" not in str(e).lower():
                    print(f"   ⚠ system_prompt: {e}")
            
            try:
                conn.execute(text("ALTER TABLE nodes ADD COLUMN tools JSON DEFAULT '[]'"))
                conn.commit()
            except Exception as e:
                if "already exists" not in str(e).lower():
                    print(f"   ⚠ tools: {e}")
            
            try:
                conn.execute(text("ALTER TABLE nodes ADD COLUMN status VARCHAR(20) DEFAULT 'active'"))
                conn.commit()
            except Exception as e:
                if "already exists" not in str(e).lower():
                    print(f"   ⚠ status: {e}")
            
            try:
                conn.execute(text("ALTER TABLE nodes ADD COLUMN is_active BOOLEAN DEFAULT TRUE"))
                conn.commit()
            except Exception as e:
                if "already exists" not in str(e).lower():
                    print(f"   ⚠ is_active: {e}")
            
            try:
                conn.execute(text("ALTER TABLE nodes ADD COLUMN version INTEGER DEFAULT 1"))
                conn.commit()
            except Exception as e:
                if "already exists" not in str(e).lower():
                    print(f"   ⚠ version: {e}")
            
            print("   ✓ New columns added to nodes")
            
            # Link nodes to projects (same id initially)
            print("🔄 Step 4: Linking nodes to projects...")
            conn.execute(text("UPDATE nodes SET project_id = id WHERE project_id IS NULL"))
            conn.commit()
            print("   ✓ Nodes linked to projects")
            
            # Migrate agent_profiles data into nodes
            print("🔄 Step 5: Migrating agent_profiles → nodes...")
            conn.execute(text("""
                UPDATE nodes n SET 
                    system_prompt = ap.system_prompt,
                    role_name = ap.role_name,
                    tools = ap.tools,
                    version = ap.version
                FROM agent_profiles ap
                WHERE ap.node_id = n.id AND ap.is_active = TRUE
            """))
            conn.commit()
            print("   ✓ Agent profiles merged into nodes")
            
        else:
            print("   ⏭ Nodes already migrated (has project_id)")
        
        # Step 6: Update chat_sessions to use project_id
        session_columns = [col["name"] for col in inspector.get_columns("chat_sessions")]
        if "project_id" not in session_columns:
            print("🔄 Step 6: Adding project_id to chat_sessions...")
            conn.execute(text("ALTER TABLE chat_sessions ADD COLUMN project_id VARCHAR(36) REFERENCES projects(id)"))
            conn.execute(text("UPDATE chat_sessions SET project_id = node_id WHERE project_id IS NULL"))
            conn.commit()
            print("   ✓ chat_sessions updated")
        else:
            print("   ⏭ chat_sessions already has project_id")
        
        # Step 7: Update uploaded_files to use project_id
        file_columns = [col["name"] for col in inspector.get_columns("uploaded_files")]
        if "project_id" not in file_columns:
            print("🔄 Step 7: Adding project_id to uploaded_files...")
            conn.execute(text("ALTER TABLE uploaded_files ADD COLUMN project_id VARCHAR(36) REFERENCES projects(id)"))
            conn.execute(text("UPDATE uploaded_files SET project_id = node_id WHERE project_id IS NULL"))
            conn.commit()
            print("   ✓ uploaded_files updated")
        else:
            print("   ⏭ uploaded_files already has project_id")
        
        # Step 8: Drop deprecated columns from nodes (optional, keep for safety)
        # print("🔄 Step 8: Cleaning up deprecated columns...")
        # conn.execute(text("ALTER TABLE nodes DROP COLUMN IF EXISTS user_id"))
        # conn.execute(text("ALTER TABLE nodes DROP COLUMN IF EXISTS lbs_access_level"))
        # conn.execute(text("ALTER TABLE nodes DROP COLUMN IF EXISTS is_archived"))
        # conn.commit()
        
        print("\n✅ Migration completed successfully!")
        
        # Verify
        print("\n📋 Final table structure:")
        for table in ["projects", "nodes", "chat_sessions", "uploaded_files"]:
            cols = [col["name"] for col in inspect(engine).get_columns(table)]
            print(f"   {table}: {cols}")

if __name__ == "__main__":
    print("=" * 60)
    print("  Migration V6: Create Project Table & Reorganize Schema")
    print("=" * 60)
    
    confirm = input("\n⚠️  This will modify your database. Continue? (yes/no): ")
    if confirm.lower() != "yes":
        print("Migration cancelled.")
        sys.exit(0)
    
    run_migration()
