from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import get_settings

# PyMongo's native async client (Motor's successor). uuidRepresentation="standard" stores
# Python UUIDs as BSON binary subtype 4, so IDs match the Postgres UUID primary keys.
_client: AsyncMongoClient | None = None


def get_client() -> AsyncMongoClient:
    global _client
    if _client is None:
        _client = AsyncMongoClient(
            get_settings().mongo_uri,
            uuidRepresentation="standard",
            tz_aware=True,
            serverSelectionTimeoutMS=5000,
        )
    return _client


def get_mongo_db() -> AsyncDatabase:
    return get_client()[get_settings().mongo_db]


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
