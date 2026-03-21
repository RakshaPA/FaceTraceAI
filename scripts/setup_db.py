"""
scripts/setup_db.py
Run once to create the PostgreSQL database and all tables.

Usage:
    python scripts/setup_db.py
"""
import json
import sys
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from db.session import init_db


def create_database_if_missing(cfg: dict):
    db = cfg["database"]
    conn = psycopg2.connect(
        host=db["host"],
        port=db["port"],
        user=db["user"],
        password=db["password"],
        dbname="postgres",  # connect to default DB first
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db["name"],))
    if not cur.fetchone():
        cur.execute(f'CREATE DATABASE "{db["name"]}"')
        print(f"[setup_db] Created database: {db['name']}")
    else:
        print(f"[setup_db] Database '{db['name']}' already exists.")
    cur.close()
    conn.close()


if __name__ == "__main__":
    cfg_path = Path(__file__).parent.parent / "config.json"
    with open(cfg_path) as f:
        config = json.load(f)

    print("[setup_db] Ensuring database exists…")
    create_database_if_missing(config)

    print("[setup_db] Creating tables…")
    init_db(config)

    print("[setup_db] ✅ Done. All tables created.")
