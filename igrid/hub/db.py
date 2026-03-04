"""SQLite schema creation for the i-grid hub."""
from pathlib import Path

import aiosqlite

_DDL_PATH = Path(__file__).parent / "hub_ddl.sql"


async def init_db(path: str) -> aiosqlite.Connection:
    db = await aiosqlite.connect(path)
    db.row_factory = aiosqlite.Row
    ddl = _DDL_PATH.read_text(encoding="utf-8")
    await db.executescript(ddl)
    # migrate existing databases: add columns if missing
    async with db.execute("PRAGMA table_info(agents)") as cur:
        cols = {row[1] for row in await cur.fetchall()}
    if "pull_mode" not in cols:
        await db.execute("ALTER TABLE agents ADD COLUMN pull_mode INTEGER NOT NULL DEFAULT 0")
    if "name" not in cols:
        await db.execute("ALTER TABLE agents ADD COLUMN name TEXT NOT NULL DEFAULT ''")
    await db.commit()
    return db
