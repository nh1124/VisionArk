"""
Database Migration System
Simple migration framework for schema evolution
"""
import os
from pathlib import Path
from datetime import datetime
from sqlalchemy import text
from models.database import get_engine, get_session


class Migration:
    """Base class for database migrations"""
    
    version: str = "000"  # Override in subclass
    description: str = ""  # Override in subclass
    
    def up(self, session):
        """Apply migration"""
        raise NotImplementedError
    
    def down(self, session):
        """Revert migration"""
        raise NotImplementedError


class MigrationRunner:
    """Executes migrations"""
    
    def __init__(self):
        self.engine = get_engine()
        self.session = get_session(self.engine)
        self.migrations_dir = Path(__file__).parent / "migrations"
        self.migrations_dir.mkdir(exist_ok=True)
        
        # Create migrations table if doesn't exist
        self._init_migrations_table()
    
    def _init_migrations_table(self):
        """Create table to track applied migrations"""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            description TEXT,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        with self.engine.connect() as conn:
            conn.execute(text(create_table_sql))
            conn.commit()
    
    def get_applied_migrations(self) -> set:
        """Get list of already applied migration versions"""
        result = self.session.execute(
            text("SELECT version FROM schema_migrations")
        )
        return {row[0] for row in result}
    
    def apply_migration(self, migration: Migration):
        """Apply a single migration"""
        print(f"Applying migration {migration.version}: {migration.description}")
        
        try:
            migration.up(self.session)
            self.session.commit()
            
            # Record migration
            self.session.execute(
                text("INSERT INTO schema_migrations (version, description) VALUES (:v, :d)"),
                {"v": migration.version, "d": migration.description}
            )
            self.session.commit()
            
            print(f"✓ Migration {migration.version} applied successfully")
        except Exception as e:
            self.session.rollback()
            print(f"✗ Migration {migration.version} failed: {str(e)}")
            raise
    
    def revert_migration(self, migration: Migration):
        """Revert a single migration"""
        print(f"Reverting migration {migration.version}: {migration.description}")
        
        try:
            migration.down(self.session)
            self.session.commit()
            
            # Remove from tracking
            self.session.execute(
                text("DELETE FROM schema_migrations WHERE version = :v"),
                {"v": migration.version}
            )
            self.session.commit()
            
            print(f"✓ Migration {migration.version} reverted successfully")
        except Exception as e:
            self.session.rollback()
            print(f"✗ Migration {migration.version} revert failed: {str(e)}")
            raise
    
    def run_migrations(self, migrations: list[Migration]):
        """Run all pending migrations"""
        applied = self.get_applied_migrations()
        pending = [m for m in migrations if m.version not in applied]
        
        if not pending:
            print("No pending migrations")
            return
        
        print(f"Found {len(pending)} pending migrations")
        for migration in sorted(pending, key=lambda m: m.version):
            self.apply_migration(migration)
    
    def close(self):
        """Close session"""
        self.session.close()


# Migration template generator
def create_migration_file(name: str):
    """
    Create a new migration file template
    
    Usage:
        python -m services.migrate create add_estimated_hours
    """
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    version = timestamp
    filename = f"{version}_{name}.py"
    migrations_dir = Path(__file__).parent / "migrations"
    migrations_dir.mkdir(exist_ok=True)
    filepath = migrations_dir / filename
    
    template = f'''"""
Migration {version}: {name.replace('_', ' ').title()}
Created: {datetime.now().isoformat()}
"""
from sqlalchemy import text
from services.migrate import Migration


class Migration{version}(Migration):
    version = "{version}"
    description = "{name.replace('_', ' ').title()}"
    
    def up(self, session):
        """Apply migration"""
        # Example: Add column
        # session.execute(text("""
        #     ALTER TABLE tasks ADD COLUMN estimated_hours FLOAT
        # """))
        pass
    
    def down(self, session):
        """Revert migration"""
        # Example: Remove column
        # session.execute(text("""
        #     ALTER TABLE tasks DROP COLUMN estimated_hours
        # """))
        pass
'''
    
    filepath.write_text(template)
    print(f"Created migration: {filepath}")
    return filepath


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "create":
        if len(sys.argv) < 3:
            print("Usage: python -m services.migrate create <migration_name>")
            sys.exit(1)
        create_migration_file(sys.argv[2])
    else:
        print("Usage:")
        print("  Create migration:  python -m services.migrate create <name>")
        print("  Run migrations:    python -m services.migrate run")
