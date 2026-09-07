import os

import asyncpg

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Set DATABASE_URL to your PostgreSQL connection URL before starting the server")


async def create_db_pool():
    return await asyncpg.create_pool(DATABASE_URL)
