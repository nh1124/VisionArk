"""
Simple backend test - minimal version
"""
import sys
from pathlib import Path

# Ensure hub_data directory exists
Path("../../hub_data").mkdir(parents=True, exist_ok=True)

# Basic imports test
print("Testing imports...")
try:
    from models.database import init_database, get_engine, get_session
    print("✅ Imports successful")
except Exception as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)

# Database initialization test
print("\nTesting database initialization...")
try:
    engine = init_database("sqlite:///../../hub_data/lbs_master.db")
    session = get_session(engine)
    print("✅ Database initialized")
except Exception as e:
    print(f"❌ Database error: {e}")
    sys.exit(1)

# LBS test removed (delegated to microservice)
print("\nℹ️ LBS Engine test skipped (remote microservice)")

print("\n✅ All basic tests passed!")
print("Backend is ready. To start the API server:")
print("   python main.py")
