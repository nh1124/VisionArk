#!/usr/bin/env python
"""
CLI tool to create API keys for AI TaskManagement OS

Usage:
    python create_api_key.py --user-id <uuid> --client-id <client_name>

Examples:
    # Create a key for development
    python create_api_key.py --user-id 00000000-0000-0000-0000-000000000001 --client-id dev-client
    
    # Create a key with specific scopes
    python create_api_key.py --user-id <uuid> --client-id frontend --scopes tasks:read tasks:write
    
    # Create an admin key
    python create_api_key.py --user-id <uuid> --client-id admin-tool --name "Admin Key" --scopes admin:*
"""
import argparse
import uuid
import sys

# Add parent directory to path for imports
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from models.database import init_database, get_session, get_engine, APIKey
from utils.security import generate_api_key, hash_api_key


def create_key(
    user_id: str,
    client_id: str,
    name: str = None,
    scopes: list = None
):
    """Create a new API key and store it in the database."""
    # Initialize database
    engine = init_database()
    session = get_session(engine)
    
    try:
        # Generate secure random key
        raw_key = generate_api_key()
        key_hash = hash_api_key(raw_key)
        
        # Create database record
        api_key = APIKey(
            id=str(uuid.uuid4()),
            key_hash=key_hash,
            user_id=user_id,
            client_id=client_id,
            name=name or f"API Key for {client_id}",
            scopes=scopes or ["*"],
            is_active=True
        )
        
        session.add(api_key)
        session.commit()
        
        print("\n" + "=" * 60)
        print("✅ API Key created successfully!")
        print("=" * 60)
        print(f"\n🔑 API KEY (SAVE THIS - shown only once):\n")
        print(f"   {raw_key}")
        print(f"\n📋 Details:")
        print(f"   Key ID:    {api_key.id}")
        print(f"   User ID:   {user_id}")
        print(f"   Client ID: {client_id}")
        print(f"   Name:      {api_key.name}")
        print(f"   Scopes:    {scopes or ['*']}")
        print(f"\n💡 Usage:")
        print(f"   curl -H \"X-API-KEY: {raw_key}\" http://localhost:8200/api/lbs/tasks")
        print("\n" + "=" * 60)
        
        return raw_key
        
    except Exception as e:
        session.rollback()
        print(f"\n❌ Failed to create API key: {e}")
        sys.exit(1)
    finally:
        session.close()


def list_keys():
    """List all API keys (without showing the actual key values)."""
    engine = get_engine()
    session = get_session(engine)
    
    try:
        keys = session.query(APIKey).all()
        
        if not keys:
            print("\n📭 No API keys found.")
            return
        
        print(f"\n📋 Found {len(keys)} API key(s):\n")
        print("-" * 80)
        
        for key in keys:
            status = "✅ Active" if key.is_active else "❌ Revoked"
            print(f"  ID:        {key.id}")
            print(f"  Client:    {key.client_id}")
            print(f"  User ID:   {key.user_id}")
            print(f"  Name:      {key.name}")
            print(f"  Scopes:    {key.scopes}")
            print(f"  Status:    {status}")
            print(f"  Created:   {key.created_at}")
            print(f"  Last Used: {key.last_used_at or 'Never'}")
            print("-" * 80)
            
    finally:
        session.close()


def revoke_key(key_id: str):
    """Revoke an API key by its ID."""
    from datetime import datetime
    
    engine = get_engine()
    session = get_session(engine)
    
    try:
        key = session.query(APIKey).filter(APIKey.id == key_id).first()
        
        if not key:
            print(f"\n❌ API key with ID '{key_id}' not found.")
            sys.exit(1)
        
        if not key.is_active:
            print(f"\n⚠️  API key '{key_id}' is already revoked.")
            return
        
        key.is_active = False
        key.revoked_at = datetime.utcnow()
        session.commit()
        
        print(f"\n✅ API key '{key_id}' has been revoked.")
        print(f"   Client: {key.client_id}")
        print(f"   Name:   {key.name}")
        
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(
        description="Manage API keys for AI TaskManagement OS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Create command
    create_parser = subparsers.add_parser("create", help="Create a new API key")
    create_parser.add_argument(
        "--user-id", "-u",
        required=True,
        help="User UUID that owns this key"
    )
    create_parser.add_argument(
        "--client-id", "-c",
        required=True,
        help="Client identifier (e.g., 'frontend', 'hub-agent')"
    )
    create_parser.add_argument(
        "--name", "-n",
        default=None,
        help="Human-readable name for the key"
    )
    create_parser.add_argument(
        "--scopes", "-s",
        nargs="+",
        default=["*"],
        help="Permission scopes (default: * for all)"
    )
    
    # List command
    subparsers.add_parser("list", help="List all API keys")
    
    # Revoke command
    revoke_parser = subparsers.add_parser("revoke", help="Revoke an API key")
    revoke_parser.add_argument(
        "key_id",
        help="ID of the key to revoke"
    )
    
    args = parser.parse_args()
    
    if args.command == "create":
        create_key(
            user_id=args.user_id,
            client_id=args.client_id,
            name=args.name,
            scopes=args.scopes
        )
    elif args.command == "list":
        list_keys()
    elif args.command == "revoke":
        revoke_key(args.key_id)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
