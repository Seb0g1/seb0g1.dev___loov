from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

PROJECT_TABLES = [
    "products",
    "draft_posts",
    "published_posts",
    "schedule_items",
    "referral_templates",
    "generation_logs",
    "publish_logs",
    "sync_status",
    "manual_exceptions",
]

TABLE_DEFINITIONS = {
    "products": """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            source VARCHAR(32) NOT NULL,
            source_id VARCHAR(128) NOT NULL,
            title VARCHAR(512) NOT NULL,
            brand VARCHAR(128),
            category VARCHAR(128) NOT NULL DEFAULT 'general',
            price FLOAT NOT NULL DEFAULT 0,
            market_price FLOAT,
            discount_percent FLOAT,
            rating FLOAT,
            reviews_count INTEGER,
            stock_count INTEGER,
            url TEXT,
            affiliate_url TEXT,
            description TEXT,
            characteristics_json TEXT,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            is_excluded BOOLEAN NOT NULL DEFAULT 0,
            is_published BOOLEAN NOT NULL DEFAULT 0,
            dedup_key VARCHAR(256) NOT NULL,
            score FLOAT NOT NULL DEFAULT 0,
            notes TEXT,
            created_at DATETIME,
            updated_at DATETIME
        )
    """,
    "sync_status": """
        CREATE TABLE IF NOT EXISTS sync_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            source VARCHAR(32) NOT NULL,
            last_synced_at DATETIME,
            last_error TEXT,
            state VARCHAR(32) NOT NULL DEFAULT 'idle',
            total_items INTEGER NOT NULL DEFAULT 0
        )
    """,
}


def _column_exists(engine: Engine, table: str, column: str) -> bool:
    inspector = inspect(engine)
    try:
        return any(col["name"] == column for col in inspector.get_columns(table))
    except Exception:
        return False


def _add_column_if_missing(engine: Engine, table: str, column_sql: str) -> None:
    column_name = column_sql.split()[0]
    if not _column_exists(engine, table, column_name):
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column_sql}"))


def ensure_project_schema(engine: Engine) -> None:
    _add_column_if_missing(engine, "products", "project_id INTEGER")
    _add_column_if_missing(engine, "draft_posts", "project_id INTEGER")
    _add_column_if_missing(engine, "published_posts", "project_id INTEGER")
    _add_column_if_missing(engine, "schedule_items", "project_id INTEGER")
    _add_column_if_missing(engine, "referral_templates", "project_id INTEGER")
    _add_column_if_missing(engine, "generation_logs", "project_id INTEGER")
    _add_column_if_missing(engine, "publish_logs", "project_id INTEGER")
    _add_column_if_missing(engine, "sync_status", "project_id INTEGER")
    _add_column_if_missing(engine, "manual_exceptions", "project_id INTEGER")

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slug VARCHAR(64) UNIQUE NOT NULL,
                    name VARCHAR(128) NOT NULL,
                    telegram_channel_url TEXT,
                    telegram_channel_id VARCHAR(128),
                    niche VARCHAR(256) NOT NULL,
                    description TEXT,
                    tagline VARCHAR(256),
                    accent_color VARCHAR(32) NOT NULL DEFAULT '#ffae42',
                    accent_secondary VARCHAR(32) NOT NULL DEFAULT '#4d7cff',
                    logo_text VARCHAR(64) NOT NULL,
                    category_focus_json TEXT,
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            )
        )
        for table_name, create_sql in TABLE_DEFINITIONS.items():
            conn.execute(text(create_sql))

    inspector = inspect(engine)
    sync_status_unique = {tuple(item.get("column_names", [])) for item in inspector.get_unique_constraints("sync_status")}
    product_unique = {tuple(item.get("column_names", [])) for item in inspector.get_unique_constraints("products")}

    if ("source",) in sync_status_unique or ("source", "project_id") not in sync_status_unique:
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS sync_status"))
            conn.execute(text(TABLE_DEFINITIONS["sync_status"]))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_sync_status_project_id ON sync_status (project_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_sync_status_source ON sync_status (source)"))

    if ("source", "source_id") in product_unique or ("project_id", "source", "source_id") not in product_unique:
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS products"))
            conn.execute(text(TABLE_DEFINITIONS["products"]))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_products_project_id ON products (project_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_products_source ON products (source)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_products_source_id ON products (source_id)"))

    with engine.begin() as conn:
        row = conn.execute(text("SELECT id FROM projects WHERE slug = 'techno-halava'")).fetchone()
        if row:
            default_project_id = row[0]
        else:
            default_project_id = None

        if default_project_id is None:
            # inserted later by seed_defaults; skip backfill until seed exists
            return

        for table in PROJECT_TABLES:
            conn.execute(text(f"UPDATE {table} SET project_id = :project_id WHERE project_id IS NULL"), {"project_id": default_project_id})
