# Custom Database Models

Integrations often need their own persistent storage. VisionArk makes this easy by providing a dynamic discovery system for SQLAlchemy models.

## 1. Defining Models

Create a `models.py` file in your integration directory. Use the shared `Base` from `models.database`.

### Example
```python
from sqlalchemy import Column, String, JSON, Integer, ForeignKey
from models.database import Base

class MyIntegrationData(Base):
    __tablename__ = "integr_mysystem_data"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), index=True)
    state_payload = Column(JSON, default=dict)
```

## 2. Naming Conventions

To prevent collisions between different integrations or the core system:
- **Prefix Table Names**: Always start your table name with `integr_[system]_`. 
- **Example**: `integr_calendar_events`, `integr_line_mapping`.

## 3. Automatic Registration

You don't need to manually import your models into the global database setup. The system's startup sequence includes a `discover_integration_models()` step that:
1. Searches for `models.py` in all `integrations/` subdirectories.
2. Dynamically imports them.
3. This triggers the SQLAlchemy declarative system to include these tables in `Base.metadata`.

## 4. Initialization & Migrations

Since the core uses `Base.metadata.create_all()`, your new tables will be automatically created the next time the backend starts.

---
> [!WARNING]
> While `create_all()` handles new tables, it does not handle schema migrations for existing ones. For complex schema changes, you may need to manually execute migration scripts or use the system's internal migration utility in `models/database.py`.
