import asyncpg #tells pythin how to connect to postgreSQL using asyncpg

DATABASE_URL = "postgresql://chat_user:check222@localhost:5432/chat_app"

async def create_db_pool():
    return await asyncpg.create_pool(DATABASE_URL)