"""
MongoDB connection helper.
Provides a singleton MongoClient and collection accessors.
"""
from pymongo import MongoClient, ASCENDING
from pymongo.collection import Collection
from app.core.config import settings

_client: MongoClient | None = None


def _get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=3000)
    return _client


def get_image_collection() -> Collection:
    """Return the word_images collection, creating the index if needed."""
    client = _get_client()
    db = client[settings.MONGODB_DATABASE]
    col = db["word_images"]
    col.create_index([("cache_key", ASCENDING)], unique=True, background=True)
    return col
