"""
Comprehensive Database Seeding Script
Seeds vocabulary words with English-only data, then uses the local LLM (Ollama/Qwen)
to auto-generate Cantonese translations, Jyutping, definitions and examples.

Only seeds concrete, camera-detectable objects (no abstract concepts, verbs, or places).

Usage:
  python seed_database.py              # Normal seed (skips if already seeded)
  python seed_database.py --force      # Force re-seed all data
  python seed_database.py --skip-llm   # Seed English only, skip Cantonese generation
  python seed_database.py --repair     # Re-generate Cantonese for words with bad jyutping (Mandarin Pinyin)
"""
import asyncio
import re
import sys
import uuid
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
# Import all models to ensure relationships are configured
from app.models.user import User, Child
from app.models.vocabulary import Word, Category, WordProgress
from app.models.content import Story, Game, Mission
from app.models.analytics import LearningSession, DailyStats, Achievement
from app.models.parent_analytics import DailyLearningStats, LearningInsight, WeeklyReport, ParentalControl
from app.models.generated_sentences import GeneratedSentence
from app.models.daily_words import DailyWordTracking
from app.services.curated_word_images import get_curated_word_image_url
from app.services.image_generation_service import _cache_key, _cached_image_path


async def generate_cantonese_for_word(enhancement_service, word_english: str, category: str) -> dict:
    """Use LLM to generate Cantonese content for a word."""
    try:
        result = await enhancement_service.enhance_word(
            word=word_english,
            source=f"seed_{category}",
            max_retries=2
        )
        return {
            "word_cantonese": result.word_cantonese,
            "jyutping": result.jyutping,
            "definition_cantonese": result.definition_cantonese,
            "example_cantonese": result.example_cantonese,
        }
    except Exception as e:
        print(f"  ⚠️  LLM failed for '{word_english}': {e}")
        return {
            "word_cantonese": "",
            "jyutping": "",
            "definition_cantonese": "",
            "example_cantonese": "",
        }


def _is_valid_jyutping(jyutping: str) -> bool:
    """Return True if jyutping looks like real Cantonese (has tone digit 1-6, no Pinyin diacritics)."""
    if not jyutping or not jyutping.strip():
        return False
    has_tone_digit = bool(re.search(r'[1-6]', jyutping))
    has_pinyin_diacritic = bool(re.search(r'[āáǎàōóǒūúǔùīíǐìēéěèǖǘǚǜ]', jyutping, re.IGNORECASE))
    return has_tone_digit and not has_pinyin_diacritic


def _is_real_image_url(value: str | None) -> bool:
    return bool(
        value and (
            value.startswith("http://")
            or value.startswith("https://")
            or value.startswith("/")
        )
    )


def _resolve_cached_image_url(word: str, word_cantonese: str, image_url: str | None) -> str | None:
    curated_image_url = get_curated_word_image_url(word)
    if curated_image_url:
        return curated_image_url

    if _is_real_image_url(image_url):
        return image_url

    cached_path = _cached_image_path(_cache_key(word, word_cantonese or ""))
    if not cached_path:
        return image_url

    return f"/uploads/images/words/{cached_path.name}"


async def repair_mandarin_words():
    """
    --repair mode: Scan all words in the DB for invalid jyutping (Mandarin Pinyin diacritics
    or missing tone digits) and re-run LLM generation for those words only.
    """
    print("\n🔧 REPAIR MODE: Scanning for words with invalid Jyutping (Mandarin Pinyin)...\n")

    from app.services.word_enhancement_service import WordEnhancementService
    from app.services.llm_service import LLMProvider
    enhancement_service = WordEnhancementService(provider=LLMProvider.OLLAMA)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Word))
        all_words = result.scalars().all()

        bad_words = [
            w for w in all_words
            if w.jyutping and not _is_valid_jyutping(w.jyutping)
        ]
        missing_words = [
            w for w in all_words
            if not w.jyutping or not w.jyutping.strip()
        ]

        print(f"  Found {len(bad_words)} words with bad jyutping (Pinyin diacritics)")
        print(f"  Found {len(missing_words)} words with missing jyutping")

        targets = bad_words + [w for w in missing_words if w not in bad_words]
        total = len(targets)

        if total == 0:
            print("\n✅ No repairs needed — all jyutping looks valid!\n")
            return

        print(f"  Re-generating Cantonese for {total} words...\n")

        fixed = 0
        failed = 0
        for i, word_obj in enumerate(targets, 1):
            print(f"  🤖 [{i}/{total}] Repairing: {word_obj.word} (current jyutping: '{word_obj.jyutping}')...", end=" ", flush=True)
            cantonese_data = await generate_cantonese_for_word(
                enhancement_service, word_obj.word, "repair"
            )
            if cantonese_data["word_cantonese"] and _is_valid_jyutping(cantonese_data["jyutping"]):
                word_obj.word_cantonese = cantonese_data["word_cantonese"]
                word_obj.jyutping = cantonese_data["jyutping"]
                word_obj.definition_cantonese = cantonese_data["definition_cantonese"]
                word_obj.example_cantonese = cantonese_data["example_cantonese"]
                fixed += 1
                print(f"✓ {cantonese_data['word_cantonese']} ({cantonese_data['jyutping']})")
            else:
                failed += 1
                print(f"✗ LLM still returned invalid jyutping: '{cantonese_data.get('jyutping', '')}' (skipped)")

            await asyncio.sleep(0.3)
            if i % 10 == 0:
                await db.commit()
                print(f"  💾 Saved progress ({i}/{total})...")

        await db.commit()
        print(f"\n✅ Repair complete: {fixed} fixed, {failed} could not be repaired\n")


async def seed_comprehensive_data():
    """Main seeding function with comprehensive vocabulary data"""
    async with AsyncSessionLocal() as db:
        # Check if data already exists
        result = await db.execute(select(Category))
        existing_categories = result.scalars().all()

        result = await db.execute(select(Word))
        existing_words = result.scalars().all()

        # Allow re-seeding with --force flag
        force_reseed = "--force" in sys.argv
        skip_llm = "--skip-llm" in sys.argv

        if not force_reseed and existing_categories and len(existing_categories) >= 12 and existing_words and len(existing_words) >= 130:
            print(f"✓ Database already has {len(existing_categories)} categories and {len(existing_words)} words")
            print("\n✅ Database already seeded with comprehensive data!")
            return

        print("🌱 Starting comprehensive database seeding...\n")

        # ========== CATEGORIES (12 — all object-focused, no Places) ==========
        print("📚 Creating categories...")

        categories_data = [
            {"name": "Animals", "name_cantonese": "動物", "icon": "🦁", "color": "bg-sunny",
             "description": "Learn about different animals and pets", "description_cantonese": "認識唔同嘅動物同寵物", "sort_order": 1},
            {"name": "Food", "name_cantonese": "食物", "icon": "🍎", "color": "bg-coral",
             "description": "Learn about different foods and drinks", "description_cantonese": "認識唔同嘅食物同飲品", "sort_order": 2},
            {"name": "Fruits & Vegetables", "name_cantonese": "蔬果", "icon": "🥬", "color": "bg-emerald",
             "description": "Learn about different fruits and vegetables", "description_cantonese": "認識唔同嘅生果同蔬菜", "sort_order": 3},
            {"name": "Toys", "name_cantonese": "玩具", "icon": "🧸", "color": "bg-sky",
             "description": "Learn about different toys", "description_cantonese": "認識唔同嘅玩具", "sort_order": 4},
            {"name": "Nature", "name_cantonese": "大自然", "icon": "🌳", "color": "bg-mint",
             "description": "Learn about plants", "description_cantonese": "認識植物", "sort_order": 5},
            {"name": "Stationery", "name_cantonese": "文具", "icon": "✏️", "color": "bg-lavender",
             "description": "Learn about school supplies", "description_cantonese": "認識學校文具", "sort_order": 6},
            {"name": "Transportation", "name_cantonese": "交通工具", "icon": "🚗", "color": "bg-ocean",
             "description": "Learn about vehicles and transportation", "description_cantonese": "認識交通工具", "sort_order": 7},
            {"name": "Household", "name_cantonese": "日常物品", "icon": "🏠", "color": "bg-amber",
             "description": "Learn about everyday household objects", "description_cantonese": "認識日常生活物品", "sort_order": 8},
            {"name": "Kitchen", "name_cantonese": "廚具", "icon": "🍳", "color": "bg-orange",
             "description": "Learn about kitchen tools and tableware", "description_cantonese": "認識廚房工具同餐具", "sort_order": 9},
            {"name": "Bathroom", "name_cantonese": "浴室用品", "icon": "🛁", "color": "bg-cyan",
             "description": "Learn about bathroom and hygiene items", "description_cantonese": "認識浴室同衛生用品", "sort_order": 10},
            {"name": "Electronics", "name_cantonese": "電子產品", "icon": "📱", "color": "bg-indigo",
             "description": "Learn about electronic devices", "description_cantonese": "認識電子產品", "sort_order": 11},
            {"name": "Clothing", "name_cantonese": "衣服", "icon": "👕", "color": "bg-pink",
             "description": "Learn about clothes and accessories", "description_cantonese": "認識衣服同飾物", "sort_order": 12},
        ]

        categories = {}

        # Clean up old categories that are no longer needed
        from sqlalchemy import delete as sa_delete
        old_category_names = ["Actions", "Colors", "Family", "Body Parts", "Numbers", "Shapes", "Places"]
        for old_cat_name in old_category_names:
            result = await db.execute(select(Category).where(Category.name == old_cat_name))
            old_cat = result.scalars().first()
            if old_cat:
                old_words_result = await db.execute(select(Word).where(Word.category == old_cat.id))
                old_word_ids = [w.id for w in old_words_result.scalars().all()]
                if old_word_ids:
                    for wid in old_word_ids:
                        await db.execute(sa_delete(WordProgress).where(WordProgress.word_id == wid))
                        await db.execute(sa_delete(GeneratedSentence).where(GeneratedSentence.word_id == wid))
                        await db.execute(sa_delete(Word).where(Word.id == wid))
                await db.delete(old_cat)
                await db.commit()
                print(f"🗑️  Removed old '{old_cat_name}' category and its words")
        print()

        for cat_data in categories_data:
            result = await db.execute(select(Category).where(Category.name == cat_data["name"]))
            category = result.scalars().first()

            if category:
                for key, value in cat_data.items():
                    if key not in ["name"]:
                        setattr(category, key, value)
                print(f"✓ Updated category: {cat_data['name']} ({cat_data['name_cantonese']})")
            else:
                category = Category(id=str(uuid.uuid4()), **cat_data)
                db.add(category)
                print(f"✓ Created category: {cat_data['name']} ({cat_data['name_cantonese']})")

            categories[cat_data["name"]] = category

        await db.commit()
        print(f"\n✅ Processed {len(categories)} categories\n")

        # ========== VOCABULARY WORDS (English-only, all concrete nouns) ==========
        # Cantonese fields left empty — will be filled by LLM
        print("📝 Creating vocabulary words...\n")

        words_data = [
            # ========== ANIMALS (12 words) ==========
            {"word": "Cat", "category": "Animals", "pronunciation": "kat", "difficulty": "EASY", "definition": "A small furry pet that says meow", "image_url": "🐱", "physical_action": "Move hands like cat paws and say 'meow'", "contexts": ["pets", "home", "animals"], "related_words": []},
            {"word": "Dog", "category": "Animals", "pronunciation": "dawg", "difficulty": "EASY", "definition": "A friendly pet that says woof", "image_url": "🐶", "physical_action": "Pant like a dog and wag your 'tail'", "contexts": ["pets", "home", "animals"], "related_words": []},
            {"word": "Fish", "category": "Animals", "pronunciation": "fish", "difficulty": "EASY", "definition": "An animal that lives in water", "image_url": "🐟", "physical_action": "Move your hands like swimming fish", "contexts": ["water", "ocean", "pets"], "related_words": []},
            {"word": "Bird", "category": "Animals", "pronunciation": "burd", "difficulty": "EASY", "definition": "An animal with wings that can fly", "image_url": "🐦", "physical_action": "Flap arms like wings and chirp", "contexts": ["sky", "nature", "trees"], "related_words": []},
            {"word": "Rabbit", "category": "Animals", "pronunciation": "rab-it", "difficulty": "EASY", "definition": "A soft furry animal with long ears that hops", "image_url": "🐰", "physical_action": "Hop like a bunny", "contexts": ["garden", "pets", "farm"], "related_words": []},
            {"word": "Panda", "category": "Animals", "pronunciation": "pan-duh", "difficulty": "MEDIUM", "definition": "A big black and white bear that eats bamboo", "image_url": "🐼", "physical_action": "Pretend to munch on bamboo", "contexts": ["zoo", "animals", "china"], "related_words": []},
            {"word": "Cow", "category": "Animals", "pronunciation": "kow", "difficulty": "EASY", "definition": "A big farm animal that gives us milk", "image_url": "🐄", "physical_action": "Make a mooing sound", "contexts": ["farm", "animals", "milk"], "related_words": []},
            {"word": "Horse", "category": "Animals", "pronunciation": "hawrs", "difficulty": "EASY", "definition": "A big animal you can ride", "image_url": "🐴", "physical_action": "Gallop in place", "contexts": ["farm", "animals", "ride"], "related_words": []},
            {"word": "Pig", "category": "Animals", "pronunciation": "pig", "difficulty": "EASY", "definition": "A pink farm animal that oinks", "image_url": "🐷", "physical_action": "Make a snorting sound", "contexts": ["farm", "animals", "pink"], "related_words": []},
            {"word": "Sheep", "category": "Animals", "pronunciation": "sheep", "difficulty": "EASY", "definition": "A fluffy farm animal with wool", "image_url": "🐑", "physical_action": "Make a baa sound", "contexts": ["farm", "animals", "wool"], "related_words": []},
            {"word": "Chicken", "category": "Animals", "word_cantonese": "雞", "jyutping": "gai1", "pronunciation": "chik-in", "difficulty": "EASY", "definition": "A common farm bird we see every day", "image_url": "🐔", "physical_action": "Flap arms and cluck like a chicken", "contexts": ["farm", "animals", "food"], "related_words": []},
            {"word": "Duck", "category": "Animals", "word_cantonese": "鴨", "jyutping": "aap3", "pronunciation": "duk", "difficulty": "EASY", "definition": "A bird that swims and quacks", "image_url": "🦆", "physical_action": "Waddle and say quack quack", "contexts": ["farm", "animals", "water"], "related_words": []},

            # ========== FOOD (16 words) ==========
            {"word": "Apple", "category": "Food", "pronunciation": "ap-uhl", "difficulty": "EASY", "definition": "A round red or green fruit", "image_url": "🍎", "physical_action": "Pretend to take a big bite", "contexts": ["fruit", "healthy", "snack"], "related_words": []},
            {"word": "Banana", "category": "Food", "pronunciation": "buh-nan-uh", "difficulty": "EASY", "definition": "A long yellow fruit that you peel", "image_url": "🍌", "physical_action": "Pretend to peel and eat a banana", "contexts": ["fruit", "snack", "yellow"], "related_words": []},
            {"word": "Rice", "category": "Food", "pronunciation": "rahys", "difficulty": "EASY", "definition": "A common food we eat every day", "image_url": "🍚", "physical_action": "Pretend to eat rice with chopsticks", "contexts": ["meal", "dinner", "daily"], "related_words": []},
            {"word": "Noodles", "category": "Food", "pronunciation": "noo-dlz", "difficulty": "EASY", "definition": "Long thin food made from flour", "image_url": "🍜", "physical_action": "Pretend to slurp noodles", "contexts": ["meal", "dinner", "soup"], "related_words": []},
            {"word": "Egg", "category": "Food", "pronunciation": "eg", "difficulty": "EASY", "definition": "A round food that comes from chickens", "image_url": "🥚", "physical_action": "Pretend to crack an egg", "contexts": ["breakfast", "cooking"], "related_words": []},
            {"word": "Milk", "category": "Food", "pronunciation": "milk", "difficulty": "EASY", "definition": "A white drink that's good for you", "image_url": "🥛", "physical_action": "Pretend to drink from a glass", "contexts": ["drink", "breakfast", "healthy"], "related_words": []},
            {"word": "Bread", "category": "Food", "pronunciation": "bred", "difficulty": "EASY", "definition": "Soft food made from flour that you can toast", "image_url": "🍞", "physical_action": "Pretend to tear and eat bread", "contexts": ["breakfast", "toast"], "related_words": []},
            {"word": "Orange", "category": "Food", "pronunciation": "or-inj", "difficulty": "MEDIUM", "definition": "A round orange fruit with vitamin C", "image_url": "🍊", "physical_action": "Pretend to peel an orange", "contexts": ["fruit", "healthy", "juice"], "related_words": []},
            {"word": "Carrot", "category": "Food", "pronunciation": "kar-uht", "difficulty": "MEDIUM", "definition": "A long orange vegetable that rabbits love", "image_url": "🥕", "physical_action": "Pretend to munch a carrot", "contexts": ["vegetable", "healthy", "crunchy"], "related_words": []},
            {"word": "Pizza", "category": "Food", "pronunciation": "peet-suh", "difficulty": "EASY", "definition": "A round flat food with cheese and toppings", "image_url": "🍕", "physical_action": "Pretend to eat a slice of pizza", "contexts": ["meal", "cheese", "party"], "related_words": []},
            {"word": "Ice Cream", "category": "Food", "pronunciation": "ahys kreem", "difficulty": "EASY", "definition": "A cold sweet treat that melts", "image_url": "🍦", "physical_action": "Pretend to lick an ice cream cone", "contexts": ["dessert", "sweet", "cold"], "related_words": []},
            {"word": "Cake", "category": "Food", "pronunciation": "keyk", "difficulty": "EASY", "definition": "A sweet food you eat on birthdays", "image_url": "🎂", "physical_action": "Pretend to blow out candles", "contexts": ["birthday", "sweet", "party"], "related_words": []},
            {"word": "Watermelon", "category": "Food", "pronunciation": "waw-ter-mel-uhn", "difficulty": "MEDIUM", "definition": "A big green fruit with red inside", "image_url": "🍉", "physical_action": "Pretend to hold a big slice", "contexts": ["fruit", "summer", "juicy"], "related_words": []},
            {"word": "Cookie", "category": "Food", "pronunciation": "kuk-ee", "difficulty": "EASY", "definition": "A small sweet baked treat", "image_url": "🍪", "physical_action": "Pretend to dunk a cookie in milk", "contexts": ["snack", "sweet", "baked"], "related_words": []},
            {"word": "Candy", "category": "Food", "pronunciation": "kan-dee", "difficulty": "EASY", "definition": "A small sweet treat", "image_url": "🍬", "physical_action": "Pretend to unwrap and eat candy", "contexts": ["sweet", "treat", "snack"], "related_words": []},
            {"word": "Chocolate", "category": "Food", "pronunciation": "chok-lit", "difficulty": "MEDIUM", "definition": "A sweet brown food made from cocoa", "image_url": "🍫", "physical_action": "Pretend to break and eat chocolate", "contexts": ["sweet", "treat", "brown"], "related_words": []},

            # ========== FRUITS & VEGETABLES (8 words) ==========
            {"word": "Grapes", "category": "Fruits & Vegetables", "pronunciation": "grayps", "difficulty": "EASY", "definition": "Small round fruits that grow in bunches", "image_url": "🍇", "physical_action": "Pretend to pick and eat grapes", "contexts": ["fruit", "sweet", "snack"], "related_words": []},
            {"word": "Mango", "category": "Fruits & Vegetables", "pronunciation": "mang-goh", "difficulty": "EASY", "definition": "A sweet tropical yellow fruit", "image_url": "🥭", "physical_action": "Pretend to slice a mango", "contexts": ["fruit", "tropical", "sweet"], "related_words": []},
            {"word": "Strawberry", "category": "Fruits & Vegetables", "pronunciation": "straw-beh-ree", "difficulty": "MEDIUM", "definition": "A small red heart-shaped fruit", "image_url": "🍓", "physical_action": "Pretend to pick strawberries", "contexts": ["fruit", "red", "sweet"], "related_words": []},
            {"word": "Corn", "category": "Fruits & Vegetables", "pronunciation": "korn", "difficulty": "EASY", "definition": "A yellow vegetable with kernels on a cob", "image_url": "🌽", "physical_action": "Pretend to eat corn on the cob", "contexts": ["vegetable", "yellow", "farm"], "related_words": []},
            {"word": "Tomato", "category": "Fruits & Vegetables", "pronunciation": "tuh-may-toh", "difficulty": "EASY", "definition": "A round red fruit used in cooking", "image_url": "🍅", "physical_action": "Pretend to slice a tomato", "contexts": ["vegetable", "red", "cooking"], "related_words": []},
            {"word": "Potato", "category": "Fruits & Vegetables", "pronunciation": "puh-tey-toh", "difficulty": "EASY", "definition": "A brown root vegetable", "image_url": "🥔", "physical_action": "Pretend to dig up a potato", "contexts": ["vegetable", "cooking", "farm"], "related_words": []},
            {"word": "Mushroom", "category": "Fruits & Vegetables", "pronunciation": "muhsh-room", "difficulty": "MEDIUM", "definition": "A small umbrella-shaped food", "image_url": "🍄", "physical_action": "Make an umbrella shape with hand", "contexts": ["vegetable", "cooking", "soup"], "related_words": []},
            {"word": "Lychee", "category": "Fruits & Vegetables", "pronunciation": "lee-chee", "difficulty": "MEDIUM", "definition": "A small sweet tropical fruit with rough red skin", "image_url": "🍒", "physical_action": "Pretend to peel a lychee", "contexts": ["fruit", "tropical", "sweet"], "related_words": []},

            # ========== TOYS (8 words) ==========
            {"word": "Ball", "category": "Toys", "pronunciation": "bawl", "difficulty": "EASY", "definition": "A round toy you can throw and kick", "image_url": "⚽", "physical_action": "Pretend to kick a ball", "contexts": ["play", "sport", "outside"], "related_words": []},
            {"word": "Doll", "category": "Toys", "pronunciation": "dol", "difficulty": "EASY", "definition": "A small toy that looks like a person", "image_url": "🧸", "physical_action": "Pretend to hug a toy", "contexts": ["play", "toy", "home"], "related_words": []},
            {"word": "Teddy Bear", "category": "Toys", "pronunciation": "ted-ee bair", "difficulty": "EASY", "definition": "A soft cuddly bear toy", "image_url": "🧸", "physical_action": "Hug an imaginary teddy bear", "contexts": ["toy", "soft", "sleep"], "related_words": []},
            {"word": "Blocks", "category": "Toys", "pronunciation": "bloks", "difficulty": "EASY", "definition": "Colorful building pieces you stack", "image_url": "🧱", "physical_action": "Pretend to stack blocks", "contexts": ["build", "play", "create"], "related_words": []},
            {"word": "Kite", "category": "Toys", "pronunciation": "kyt", "difficulty": "MEDIUM", "definition": "A toy that flies high in the wind", "image_url": "🪁", "physical_action": "Pretend to hold a kite string", "contexts": ["outside", "wind", "fly"], "related_words": []},
            {"word": "Balloon", "category": "Toys", "pronunciation": "buh-loon", "difficulty": "EASY", "definition": "A colorful inflatable toy", "image_url": "🎈", "physical_action": "Pretend to blow up a balloon", "contexts": ["party", "play", "colorful"], "related_words": []},
            {"word": "Puzzle", "category": "Toys", "pronunciation": "puhz-uhl", "difficulty": "MEDIUM", "definition": "A picture cut into pieces you put together", "image_url": "🧩", "physical_action": "Pretend to fit puzzle pieces", "contexts": ["toy", "think", "picture"], "related_words": []},
            {"word": "Scooter", "category": "Toys", "pronunciation": "skoo-ter", "difficulty": "MEDIUM", "definition": "A two-wheeled toy you ride standing up", "image_url": "🛴", "physical_action": "Pretend to ride a scooter", "contexts": ["toy", "ride", "outside"], "related_words": []},

            # ========== NATURE (2 words) ==========
            {"word": "Tree", "category": "Nature", "pronunciation": "tree", "difficulty": "EASY", "definition": "A tall plant with branches and leaves", "image_url": "🌳", "physical_action": "Stand tall with arms up like branches", "contexts": ["nature", "park", "green"], "related_words": []},
            {"word": "Flower", "category": "Nature", "pronunciation": "flou-er", "difficulty": "EASY", "definition": "A pretty plant with colorful petals", "image_url": "🌸", "physical_action": "Pretend to smell a flower", "contexts": ["nature", "garden", "pretty"], "related_words": []},

            # ========== STATIONERY (7 words) ==========
            {"word": "Pencil", "category": "Stationery", "pronunciation": "pen-suhl", "difficulty": "EASY", "definition": "A tool you write and draw with", "image_url": "✏️", "physical_action": "Pretend to write", "contexts": ["school", "write", "draw"], "related_words": []},
            {"word": "Crayon", "category": "Stationery", "pronunciation": "krey-on", "difficulty": "EASY", "definition": "A colorful stick you draw with", "image_url": "🖍️", "physical_action": "Pretend to color a picture", "contexts": ["school", "draw", "art"], "related_words": []},
            {"word": "Ruler", "category": "Stationery", "pronunciation": "roo-ler", "difficulty": "MEDIUM", "definition": "A long flat tool for measuring", "image_url": "📏", "physical_action": "Hold a flat hand out like a ruler", "contexts": ["school", "measure", "line"], "related_words": []},
            {"word": "Eraser", "category": "Stationery", "pronunciation": "ih-rey-ser", "difficulty": "MEDIUM", "definition": "A tool that removes pencil marks", "image_url": "🧽", "physical_action": "Pretend to rub an eraser on paper", "contexts": ["school", "fix", "clean"], "related_words": []},
            {"word": "Paper", "category": "Stationery", "pronunciation": "pey-per", "difficulty": "EASY", "definition": "A flat white sheet you write or draw on", "image_url": "📄", "physical_action": "Hold up a flat hand like paper", "contexts": ["school", "write", "draw"], "related_words": []},
            {"word": "Pen", "category": "Stationery", "pronunciation": "pen", "difficulty": "EASY", "definition": "A tool with ink for writing", "image_url": "🖊️", "physical_action": "Pretend to write with a pen", "contexts": ["school", "write", "ink"], "related_words": []},
            {"word": "Marker", "category": "Stationery", "pronunciation": "mahr-ker", "difficulty": "EASY", "definition": "A pen with bright colored ink", "image_url": "🖍️", "physical_action": "Pretend to color with a marker", "contexts": ["school", "draw", "color"], "related_words": []},

            # ========== TRANSPORTATION (6 words) ==========
            {"word": "Car", "category": "Transportation", "pronunciation": "kahr", "difficulty": "EASY", "definition": "A vehicle with four wheels", "image_url": "🚗", "physical_action": "Pretend to drive", "contexts": ["vehicle", "road", "drive"], "related_words": []},
            {"word": "Bus", "category": "Transportation", "pronunciation": "buhs", "difficulty": "EASY", "definition": "A big vehicle that carries many people", "image_url": "🚌", "physical_action": "Pretend to sit on a bus", "contexts": ["vehicle", "school", "big"], "related_words": []},
            {"word": "Train", "category": "Transportation", "pronunciation": "treyn", "difficulty": "MEDIUM", "definition": "A long vehicle that runs on tracks", "image_url": "🚂", "physical_action": "Move arms like train wheels", "contexts": ["vehicle", "tracks", "travel"], "related_words": []},
            {"word": "Bicycle", "category": "Transportation", "pronunciation": "bahy-si-kuhl", "difficulty": "MEDIUM", "definition": "A vehicle with two wheels you pedal", "image_url": "🚲", "physical_action": "Pretend to pedal a bicycle", "contexts": ["vehicle", "exercise", "fun"], "related_words": []},
            {"word": "Taxi", "category": "Transportation", "pronunciation": "tak-see", "difficulty": "EASY", "definition": "A car you pay to ride in", "image_url": "🚕", "physical_action": "Pretend to wave for a taxi", "contexts": ["vehicle", "city", "ride"], "related_words": []},
            {"word": "Subway", "category": "Transportation", "pronunciation": "suhb-way", "difficulty": "MEDIUM", "definition": "A train that goes underground", "image_url": "🚇", "physical_action": "Pretend to hold a handrail", "contexts": ["vehicle", "underground", "city"], "related_words": []},

            # ========== HOUSEHOLD OBJECTS (14 words) ==========
            {"word": "Cup", "category": "Household", "pronunciation": "kuhp", "difficulty": "EASY", "definition": "A container you drink from", "image_url": "🥤", "physical_action": "Pretend to hold and drink", "contexts": ["kitchen", "drink", "daily"], "related_words": []},
            {"word": "Spoon", "category": "Household", "pronunciation": "spoon", "difficulty": "EASY", "definition": "A tool you use to eat soup or rice", "image_url": "🥄", "physical_action": "Pretend to scoop and eat", "contexts": ["kitchen", "eat", "meal"], "related_words": []},
            {"word": "Book", "category": "Household", "pronunciation": "buk", "difficulty": "EASY", "definition": "Pages with words and pictures you read", "image_url": "📖", "physical_action": "Pretend to open and read a book", "contexts": ["school", "read", "learn"], "related_words": []},
            {"word": "Chair", "category": "Household", "pronunciation": "chair", "difficulty": "EASY", "definition": "Furniture you sit on", "image_url": "🪑", "physical_action": "Pretend to sit down", "contexts": ["home", "school", "sit"], "related_words": []},
            {"word": "Table", "category": "Household", "pronunciation": "tey-buhl", "difficulty": "EASY", "definition": "Flat furniture where you eat or work", "image_url": "🪵", "physical_action": "Pat the table", "contexts": ["home", "kitchen", "eat"], "related_words": []},
            {"word": "Bag", "category": "Household", "pronunciation": "bag", "difficulty": "EASY", "definition": "A bag you carry your things in", "image_url": "🎒", "physical_action": "Pretend to put on a backpack", "contexts": ["school", "carry", "daily"], "related_words": []},
            {"word": "Umbrella", "category": "Household", "pronunciation": "uhm-brel-uh", "difficulty": "MEDIUM", "definition": "Something you hold above you when it rains", "image_url": "☂️", "physical_action": "Pretend to open and hold an umbrella", "contexts": ["rain", "weather", "carry"], "related_words": []},
            {"word": "Clock", "category": "Household", "pronunciation": "klok", "difficulty": "MEDIUM", "definition": "A thing that tells you the time", "image_url": "🕐", "physical_action": "Make tick-tock sounds", "contexts": ["time", "home", "daily"], "related_words": []},
            {"word": "Toothbrush", "category": "Household", "pronunciation": "tooth-bruhsh", "difficulty": "MEDIUM", "definition": "A tool you use to clean your teeth", "image_url": "🪥", "physical_action": "Pretend to brush your teeth", "contexts": ["bathroom", "morning", "clean"], "related_words": []},
            {"word": "Pillow", "category": "Household", "pronunciation": "pil-oh", "difficulty": "EASY", "definition": "A soft cushion you rest your head on", "image_url": "🛏️", "physical_action": "Pretend to lay head on pillow", "contexts": ["bedroom", "sleep", "soft"], "related_words": []},
            {"word": "Blanket", "category": "Household", "pronunciation": "blang-kit", "difficulty": "EASY", "definition": "A warm cover for sleeping", "image_url": "🛏️", "physical_action": "Pretend to pull up a blanket", "contexts": ["bedroom", "sleep", "warm"], "related_words": []},
            {"word": "Broom", "category": "Household", "pronunciation": "broom", "difficulty": "MEDIUM", "definition": "A tool for sweeping the floor", "image_url": "🧹", "physical_action": "Pretend to sweep the floor", "contexts": ["home", "clean", "floor"], "related_words": []},
            {"word": "Sofa", "category": "Household", "word_cantonese": "梳化", "jyutping": "so1 faa3", "pronunciation": "soh-fuh", "difficulty": "EASY", "definition": "A big soft seat in the living room", "image_url": "🛋️", "physical_action": "Sit down and relax", "contexts": ["home", "sit", "living room"], "related_words": []},
            {"word": "Bed", "category": "Household", "word_cantonese": "牀", "jyutping": "cong4", "pronunciation": "bed", "difficulty": "EASY", "definition": "Where you sleep at night", "image_url": "🛏️", "physical_action": "Pretend to lie down and sleep", "contexts": ["bedroom", "sleep", "home"], "related_words": []},

            # ========== KITCHEN & TABLEWARE (8 words) ==========
            {"word": "Plate", "category": "Kitchen", "pronunciation": "pleyt", "difficulty": "EASY", "definition": "A flat round dish for food", "image_url": "🍽️", "physical_action": "Hold out flat hands like a plate", "contexts": ["kitchen", "eat", "meal"], "related_words": []},
            {"word": "Bowl", "category": "Kitchen", "pronunciation": "bohl", "difficulty": "EASY", "definition": "A deep round dish for soup or rice", "image_url": "🥣", "physical_action": "Cup hands like a bowl", "contexts": ["kitchen", "eat", "soup"], "related_words": []},
            {"word": "Pot", "category": "Kitchen", "pronunciation": "pot", "difficulty": "EASY", "definition": "A deep container for cooking", "image_url": "🍲", "physical_action": "Pretend to stir a pot", "contexts": ["kitchen", "cook", "soup"], "related_words": []},
            {"word": "Microwave", "category": "Kitchen", "pronunciation": "my-kroh-weyv", "difficulty": "HARD", "definition": "A machine that heats up food quickly", "image_url": "📦", "physical_action": "Pretend to press buttons and open door", "contexts": ["kitchen", "heat", "quick"], "related_words": []},
            {"word": "Fridge", "category": "Kitchen", "pronunciation": "frij", "difficulty": "MEDIUM", "definition": "A cold box that keeps food fresh", "image_url": "🧊", "physical_action": "Pretend to open a fridge door", "contexts": ["kitchen", "cold", "food"], "related_words": []},
            {"word": "Chopsticks", "category": "Kitchen", "word_cantonese": "筷子", "jyutping": "faai3 zi2", "pronunciation": "chop-stiks", "difficulty": "EASY", "definition": "Two sticks you use to eat food", "image_url": "🥢", "physical_action": "Pretend to use chopsticks to pick up food", "contexts": ["kitchen", "eat", "meal"], "related_words": []},
            {"word": "Water Bottle", "category": "Kitchen", "word_cantonese": "水樽", "jyutping": "seoi2 zeon1", "pronunciation": "waw-ter bot-uhl", "difficulty": "EASY", "definition": "A bottle you drink water from", "image_url": "🍶", "physical_action": "Pretend to drink from a bottle", "contexts": ["drink", "daily", "school"], "related_words": []},
            {"word": "Lunchbox", "category": "Kitchen", "word_cantonese": "飯盒", "jyutping": "faan6 hap6", "pronunciation": "lunch-boks", "difficulty": "EASY", "definition": "A box to carry your lunch to school", "image_url": "🍱", "physical_action": "Pretend to open a lunchbox", "contexts": ["school", "food", "meal"], "related_words": []},

            # ========== BATHROOM & HYGIENE (8 words) ==========
            {"word": "Towel", "category": "Bathroom", "pronunciation": "tou-uhl", "difficulty": "EASY", "definition": "A soft cloth for drying yourself", "image_url": "🧻", "physical_action": "Pretend to dry hands", "contexts": ["bathroom", "dry", "clean"], "related_words": []},
            {"word": "Soap", "category": "Bathroom", "pronunciation": "sohp", "difficulty": "EASY", "definition": "Something you use to wash and clean", "image_url": "🧼", "physical_action": "Pretend to wash hands with soap", "contexts": ["bathroom", "clean", "wash"], "related_words": []},
            {"word": "Shampoo", "category": "Bathroom", "pronunciation": "sham-poo", "difficulty": "MEDIUM", "definition": "A liquid you use to wash your hair", "image_url": "🧴", "physical_action": "Pretend to wash hair", "contexts": ["bathroom", "hair", "clean"], "related_words": []},
            {"word": "Toilet Paper", "category": "Bathroom", "pronunciation": "toy-lit pey-per", "difficulty": "EASY", "definition": "Soft paper used in the bathroom", "image_url": "🧻", "physical_action": "Pretend to pull toilet paper", "contexts": ["bathroom", "clean", "daily"], "related_words": []},
            {"word": "Mirror", "category": "Bathroom", "pronunciation": "mir-er", "difficulty": "EASY", "definition": "A glass that shows your reflection", "image_url": "🪞", "physical_action": "Pretend to look at your reflection", "contexts": ["bathroom", "see", "face"], "related_words": []},
            {"word": "Bathtub", "category": "Bathroom", "pronunciation": "bath-tuhb", "difficulty": "MEDIUM", "definition": "A big tub you sit in to take a bath", "image_url": "🛁", "physical_action": "Pretend to splash in water", "contexts": ["bathroom", "wash", "water"], "related_words": []},
            {"word": "Shower", "category": "Bathroom", "pronunciation": "shou-er", "difficulty": "MEDIUM", "definition": "A device that sprays water to wash you", "image_url": "🚿", "physical_action": "Pretend to shower", "contexts": ["bathroom", "wash", "water"], "related_words": []},
            {"word": "Comb", "category": "Bathroom", "word_cantonese": "梳", "jyutping": "so1", "pronunciation": "kohm", "difficulty": "EASY", "definition": "A tool you use to tidy your hair", "image_url": "🪮", "physical_action": "Pretend to comb your hair", "contexts": ["bathroom", "hair", "morning"], "related_words": []},

            # ========== ELECTRONICS (6 words) ==========
            {"word": "Phone", "category": "Electronics", "pronunciation": "fohn", "difficulty": "EASY", "definition": "A device you use to call and text people", "image_url": "📱", "physical_action": "Pretend to hold a phone to ear", "contexts": ["tech", "talk", "daily"], "related_words": []},
            {"word": "Television", "category": "Electronics", "pronunciation": "tel-uh-vizh-uhn", "difficulty": "MEDIUM", "definition": "A screen you watch shows and movies on", "image_url": "📺", "physical_action": "Pretend to hold a remote and watch", "contexts": ["tech", "watch", "home"], "related_words": []},
            {"word": "Watch", "category": "Electronics", "pronunciation": "woch", "difficulty": "EASY", "definition": "A small clock you wear on your wrist", "image_url": "⌚", "physical_action": "Point to your wrist", "contexts": ["tech", "time", "wear"], "related_words": []},
            {"word": "Lamp", "category": "Electronics", "pronunciation": "lamp", "difficulty": "EASY", "definition": "A device that gives light", "image_url": "💡", "physical_action": "Pretend to switch on a lamp", "contexts": ["home", "light", "night"], "related_words": []},
            {"word": "Fan", "category": "Electronics", "word_cantonese": "風扇", "jyutping": "fung1 sin3", "pronunciation": "fan", "difficulty": "EASY", "definition": "A spinning device that makes cool wind", "image_url": "🌀", "physical_action": "Wave hands fast like a fan spinning", "contexts": ["home", "cool", "summer"], "related_words": []},
            {"word": "Air Conditioner", "category": "Electronics", "pronunciation": "air kuhn-dish-uhn-er", "difficulty": "HARD", "definition": "A machine that makes a room cool", "image_url": "❄️", "physical_action": "Wrap arms and shiver like it is cold", "contexts": ["home", "cool", "summer"], "related_words": []},

            # ========== CLOTHING (8 words) ==========
            {"word": "Shirt", "category": "Clothing", "pronunciation": "shurt", "difficulty": "EASY", "definition": "Clothing you wear on top", "image_url": "👕", "physical_action": "Point to your shirt", "contexts": ["clothing", "wear", "daily"], "related_words": []},
            {"word": "Pants", "category": "Clothing", "pronunciation": "pants", "difficulty": "EASY", "definition": "Clothing you wear on your legs", "image_url": "👖", "physical_action": "Point to your pants", "contexts": ["clothing", "wear", "daily"], "related_words": []},
            {"word": "Shoes", "category": "Clothing", "pronunciation": "shooz", "difficulty": "EASY", "definition": "What you wear on your feet", "image_url": "👟", "physical_action": "Point to your shoes", "contexts": ["clothing", "feet", "walk"], "related_words": []},
            {"word": "Hat", "category": "Clothing", "pronunciation": "hat", "difficulty": "EASY", "definition": "What you wear on your head", "image_url": "🎩", "physical_action": "Pretend to put on a hat", "contexts": ["clothing", "head", "sun"], "related_words": []},
            {"word": "Socks", "category": "Clothing", "pronunciation": "soks", "difficulty": "EASY", "definition": "What you wear on your feet inside shoes", "image_url": "🧦", "physical_action": "Point to your socks", "contexts": ["clothing", "feet", "warm"], "related_words": []},
            {"word": "Dress", "category": "Clothing", "pronunciation": "dres", "difficulty": "MEDIUM", "definition": "A one-piece clothing", "image_url": "👗", "physical_action": "Twirl around", "contexts": ["clothing", "pretty", "special"], "related_words": []},
            {"word": "Jacket", "category": "Clothing", "pronunciation": "jak-it", "difficulty": "MEDIUM", "definition": "A warm coat you wear outside", "image_url": "🧥", "physical_action": "Pretend to zip up a jacket", "contexts": ["clothing", "warm", "cold"], "related_words": []},
            {"word": "House Slippers", "category": "Clothing", "pronunciation": "slip-erz", "difficulty": "EASY", "definition": "Soft shoes you wear at home", "image_url": "🩴", "physical_action": "Pretend to slide on slippers", "contexts": ["clothing", "home", "feet"], "related_words": []},
        ]

        # Remove words that no longer belong in the vocabulary
        from sqlalchemy import delete as sa_delete
        removed_words = [
            # Old non-object words
            "Water", "Sun", "Rain", "Moon", "Star", "Cloud", "Wind", "Grass", "Mountain",
            "Home", "School", "Park", "Store", "Beach", "Library", "Hospital",
            "Restaurant", "Supermarket", "Airport", "Zoo", "Swimming Pool",
            # Rare/zoo animals removed for being unfamiliar to HK children daily life
            "Elephant", "Lion", "Butterfly", "Monkey", "Turtle", "Shark", "Penguin", "Deer",
            # Food items removed (uncommon in daily HK child life)
            "Toast", "Sushi", "French Fries",
            # Fruits & Vegetables removed (rarely encountered by young children)
            "Pineapple", "Cucumber", "Onion", "Lemon",
            # Toys removed (uncommon or niche)
            "Robot", "Drum", "Jump Rope", "Spinning Top",
            # Stationery removed (office/adult items, not child-safe)
            "Scissors", "Glue", "Stapler", "Tape", "Paper Clip",
            # Transportation removed (rare for HK children to encounter regularly)
            "Airplane", "Boat", "Helicopter", "Ambulance",
            # Household items removed (dangerous or decorative, not everyday for children)
            "Candle", "Vase", "Key",
            # Kitchen items removed (dangerous sharp/hot tools)
            "Knife", "Wok", "Oven", "Cutting Board", "Fork",
            # Bathroom items removed
            "Cotton Swab",
            # Electronics removed (adult devices)
            "Laptop", "Camera", "Headphones", "Remote Control",
            # Clothing removed (uncommon for HK climate or daily child use)
            "Glasses", "Gloves", "Scarf", "Swimsuit",
        ]
        for rw in removed_words:
            result = await db.execute(select(Word).where(Word.word == rw))
            old_word = result.scalars().first()
            if old_word:
                await db.execute(sa_delete(WordProgress).where(WordProgress.word_id == old_word.id))
                await db.execute(sa_delete(GeneratedSentence).where(GeneratedSentence.word_id == old_word.id))
                await db.execute(sa_delete(Word).where(Word.id == old_word.id))
                print(f"🗑️  Removed non-object word: {rw}")
        await db.commit()

        # Create words with English data (Cantonese fields empty for now)
        words_created = 0
        words_updated = 0
        word_objects = {}

        for word_data in words_data:
            category_name = word_data.pop("category")
            category_id = categories[category_name].id

            # Add empty Cantonese fields
            word_data.setdefault("word_cantonese", "")
            word_data.setdefault("jyutping", "")
            word_data.setdefault("definition_cantonese", "")
            word_data.setdefault("example_cantonese", "")
            word_data.setdefault("example", word_data["definition"])

            result = await db.execute(select(Word).where(Word.word == word_data["word"]))
            existing_word = result.scalars().first()

            if existing_word:
                for key, value in word_data.items():
                    if key != "related_words":
                        setattr(existing_word, key, value)
                setattr(existing_word, "category", category_id)
                word_objects[word_data["word"]] = existing_word
                words_updated += 1
            else:
                word = Word(
                    id=str(uuid.uuid4()),
                    category=category_id,
                    **{k: v for k, v in word_data.items() if k != "related_words"}
                )
                db.add(word)
                word_objects[word_data["word"]] = word
                words_created += 1

            if (words_created + words_updated) % 20 == 0:
                print(f"  Processed {words_created + words_updated} words...")

        await db.commit()
        print(f"\n✅ Created {words_created} new words, updated {words_updated} existing words\n")

        # ========== LLM CANTONESE GENERATION ==========
        if skip_llm:
            print("⏭️  Skipping LLM Cantonese generation (--skip-llm flag)\n")
        else:
            print("🤖 Generating Cantonese translations using Ollama/Qwen...\n")
            print("   (This may take a few minutes for ~138 words)\n")

            try:
                from app.services.word_enhancement_service import WordEnhancementService
                from app.services.llm_service import LLMProvider
                enhancement_service = WordEnhancementService(provider=LLMProvider.OLLAMA)

                total = len(word_objects)
                success_count = 0
                fail_count = 0

                for i, (word_name, word_obj) in enumerate(word_objects.items(), 1):
                    # Skip words that already have valid pre-filled Cantonese (e.g. the 9 new additions)
                    if word_obj.word_cantonese and word_obj.word_cantonese != word_name and _is_valid_jyutping(word_obj.jyutping):
                        success_count += 1
                        print(f"  ⏭️  [{i}/{total}] Skipping {word_name} (pre-filled: {word_obj.word_cantonese} / {word_obj.jyutping})")
                        continue

                    print(f"  🤖 [{i}/{total}] Generating Cantonese for: {word_name}...", end=" ", flush=True)

                    cantonese_data = await generate_cantonese_for_word(
                        enhancement_service, word_name, "general"
                    )

                    if cantonese_data["word_cantonese"]:
                        word_obj.word_cantonese = cantonese_data["word_cantonese"]
                        word_obj.jyutping = cantonese_data["jyutping"]
                        word_obj.definition_cantonese = cantonese_data["definition_cantonese"]
                        word_obj.example_cantonese = cantonese_data["example_cantonese"]
                        success_count += 1
                        print(f"✓ {cantonese_data['word_cantonese']} ({cantonese_data['jyutping']})")
                    else:
                        fail_count += 1
                        print("✗ (failed, English only)")

                    # Small delay to avoid overwhelming Ollama
                    await asyncio.sleep(0.3)

                    # Commit every 20 words
                    if i % 20 == 0:
                        await db.commit()
                        print(f"  💾 Saved progress ({i}/{total})...")

                await db.commit()
                print(f"\n✅ Cantonese generation complete: {success_count} success, {fail_count} failed\n")

            except Exception as e:
                print(f"\n⚠️  LLM generation failed: {e}")
                print("   Words will have English data only. You can re-run with --force later.\n")
                await db.commit()

        print("🖼️  Syncing cached word images into PostgreSQL image_url fields...\n")
        image_updates = 0
        for word_obj in word_objects.values():
            resolved_image_url = _resolve_cached_image_url(
                word_obj.word,
                word_obj.word_cantonese,
                word_obj.image_url,
            )
            if resolved_image_url != word_obj.image_url:
                word_obj.image_url = resolved_image_url
                image_updates += 1

        await db.commit()
        print(f"✅ Synced {image_updates} cached word images into PostgreSQL\n")

        # Update category word counts
        print("📊 Updating category word counts...")
        for category in categories.values():
            result = await db.execute(
                select(Word).where(
                    Word.category == category.id,
                    Word.is_active == True
                )
            )
            word_count = len(result.scalars().all())
            category.word_count = word_count

        await db.commit()
        print("✅ Category word counts updated\n")

        # Final summary
        result = await db.execute(select(Category))
        total_categories = len(result.scalars().all())

        result = await db.execute(select(Word))
        total_words = len(result.scalars().all())

        print("=" * 60)
        print("🎉 DATABASE SEEDING COMPLETE!")
        print("=" * 60)
        print(f"📚 Total Categories: {total_categories}")
        print(f"📝 Total Words: {total_words}")
        print(f"✅ All words are concrete, camera-detectable objects")
        print(f"✅ Cantonese generated by LLM (spoken 口語, not written 書面語)")
        print(f"   - word_cantonese (e.g. 馬騮, 雀仔, 遮)")
        print(f"   - jyutping (e.g. maa5 lau1)")
        print(f"   - definition_cantonese")
        print(f"   - example_cantonese")
        print("=" * 60)
        print("\n🚀 Your vocabulary platform is ready to use!\n")


if __name__ == "__main__":
    if "--repair" in sys.argv:
        print("Running in repair mode to fix Mandarin Pinyin jyutping...\n")
        asyncio.run(repair_mandarin_words())
    else:
        print("🌱 Starting comprehensive database seeding...\n")
        asyncio.run(seed_comprehensive_data())
