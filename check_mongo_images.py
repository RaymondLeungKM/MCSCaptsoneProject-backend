"""
Inspect pre-generated images stored in MongoDB.

Usage:
  python check_mongo_images.py               # Summary counts
  python check_mongo_images.py --list        # List all words stored
  python check_mongo_images.py --word "猫"   # Check a specific word
  python check_mongo_images.py --export cat.jpg --word "cat"  # Save image to disk
"""
import argparse
import sys
from pathlib import Path

from app.core.config import settings


def get_collection():
    if not settings.MONGODB_ENABLED or not settings.MONGODB_URI:
        print("❌ MongoDB not enabled. Check MONGODB_ENABLED and MONGODB_URI in .env")
        sys.exit(1)
    from app.db.mongodb import get_image_collection
    return get_image_collection()


def cmd_summary(col):
    total = col.count_documents({})
    print(f"📦 Total images in MongoDB: {total}")
    if total == 0:
        return
    # Breakdown by size
    pipeline = [
        {"$project": {"size": {"$bsonSize": "$$ROOT"}}},
        {"$group": {"_id": None, "total_bytes": {"$sum": "$size"}, "count": {"$sum": 1}}},
    ]
    agg = list(col.aggregate(pipeline))
    if agg:
        mb = agg[0]["total_bytes"] / (1024 * 1024)
        print(f"💾 Total storage used: {mb:.1f} MB")
    # Sample the most recent 5
    recent = list(col.find({}, {"word": 1, "word_cantonese": 1, "updated_at": 1, "content_type": 1})
                  .sort("updated_at", -1).limit(5))
    if recent:
        print("\n🕐 Most recently generated:")
        for doc in recent:
            ts = doc.get("updated_at", "?")
            print(f"  • {doc.get('word_cantonese', '')} / {doc.get('word', '')}  [{doc.get('content_type', '?')}]  {ts}")


def cmd_list(col):
    docs = list(col.find({}, {"word": 1, "word_cantonese": 1, "cache_key": 1, "updated_at": 1})
                .sort("word", 1))
    if not docs:
        print("No images stored in MongoDB yet.")
        return
    print(f"{'#':<5} {'Cantonese':<20} {'English':<25} {'Updated'}")
    print("-" * 70)
    for i, doc in enumerate(docs, 1):
        ts = str(doc.get("updated_at", ""))[:19]
        print(f"{i:<5} {doc.get('word_cantonese', ''):<20} {doc.get('word', ''):<25} {ts}")
    print(f"\nTotal: {len(docs)}")


def cmd_word(col, word: str):
    import hashlib
    # Try exact word or word_cantonese match, or cache_key match
    doc = col.find_one(
        {"$or": [{"word": word}, {"word_cantonese": word}]},
        {"image_data": 0},  # exclude binary for display
    )
    if not doc:
        # Try computing the cache_key
        ck = hashlib.md5(word.strip().encode()).hexdigest()
        doc = col.find_one({"cache_key": ck}, {"image_data": 0})
    if not doc:
        print(f"❌ No image found for '{word}'")
        return
    print(f"✅ Found image for '{word}':")
    print(f"   word          : {doc.get('word')}")
    print(f"   word_cantonese: {doc.get('word_cantonese')}")
    print(f"   cache_key     : {doc.get('cache_key')}")
    print(f"   content_type  : {doc.get('content_type')}")
    print(f"   created_at    : {doc.get('created_at')}")
    print(f"   updated_at    : {doc.get('updated_at')}")
    size = len(doc.get("image_data", b"")) if "image_data" in doc else "?"
    print(f"   size          : {size} bytes")


def cmd_export(col, word: str, output: str):
    import hashlib
    doc = col.find_one({"$or": [{"word": word}, {"word_cantonese": word}]})
    if not doc:
        ck = hashlib.md5(word.strip().encode()).hexdigest()
        doc = col.find_one({"cache_key": ck})
    if not doc or not doc.get("image_data"):
        print(f"❌ No image found for '{word}'")
        return
    path = Path(output)
    path.write_bytes(bytes(doc["image_data"]))
    print(f"✅ Saved {len(bytes(doc['image_data'])) // 1024}KB image to {path}")


def main():
    parser = argparse.ArgumentParser(description="Inspect MongoDB pre-generated images")
    parser.add_argument("--list", action="store_true", help="List all stored images")
    parser.add_argument("--word", type=str, default=None, help="Check a specific word (English or Cantonese)")
    parser.add_argument("--export", type=str, default=None,
                        help="Save image to this file path (requires --word)")
    args = parser.parse_args()

    col = get_collection()

    if args.export:
        if not args.word:
            print("❌ --export requires --word")
            sys.exit(1)
        cmd_export(col, args.word, args.export)
    elif args.word:
        cmd_word(col, args.word)
    elif args.list:
        cmd_list(col)
    else:
        cmd_summary(col)


if __name__ == "__main__":
    main()
