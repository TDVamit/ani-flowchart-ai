from motor.motor_asyncio import AsyncIOMotorClient
from config import settings

client: AsyncIOMotorClient = None


async def connect_db():
    global client
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client[settings.mongodb_db_name]
    # Create indexes
    await db.daily_entries.create_index([("project_id", 1), ("entry_date", -1)])
    await db.reports.create_index([("project_id", 1), ("report_date", -1)])
    await db.context_store.create_index([("project_id", 1)], unique=True)


async def close_db():
    global client
    if client:
        client.close()


def get_db():
    return client[settings.mongodb_db_name]
