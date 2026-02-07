"""
Comprehensive Database Seeding Script
Seeds vocabulary words with complete data for all columns including:
- English and Cantonese (Traditional Chinese with Jyutping)
- Physical actions, contexts, related words
- Multiple categories with extensive vocabulary
"""
import asyncio
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


async def seed_comprehensive_data():
    """Main seeding function with comprehensive vocabulary data"""
    async with AsyncSessionLocal() as db:
        # Check if data already exists
        result = await db.execute(select(Category))
        existing_categories = result.scalars().all()
        
        result = await db.execute(select(Word))
        existing_words = result.scalars().all()
        
        if existing_categories and len(existing_categories) >= 10 and existing_words and len(existing_words) >= 80:
            print(f"✓ Database already has {len(existing_categories)} categories and {len(existing_words)} words")
            print("\n✅ Database already seeded with comprehensive data!")
            return
        
        print("🌱 Starting comprehensive database seeding...\n")
        
        # ========== CATEGORIES ==========
        print("📚 Creating categories...")
        
        categories_data = [
            {
                "name": "Animals",
                "name_cantonese": "動物",
                "icon": "🦁",
                "color": "bg-sunny",
                "description": "Learn about different animals and pets",
                "description_cantonese": "認識不同嘅動物同寵物",
                "sort_order": 1
            },
            {
                "name": "Food",
                "name_cantonese": "食物",
                "icon": "🍎",
                "color": "bg-coral",
                "description": "Learn about different foods and drinks",
                "description_cantonese": "認識不同嘅食物同飲品",
                "sort_order": 2
            },
            {
                "name": "Colors",
                "name_cantonese": "顏色",
                "icon": "🎨",
                "color": "bg-sky",
                "description": "Learn about different colors",
                "description_cantonese": "認識唔同嘅顏色",
                "sort_order": 3
            },
            {
                "name": "Nature",
                "name_cantonese": "大自然",
                "icon": "🌳",
                "color": "bg-mint",
                "description": "Learn about nature and weather",
                "description_cantonese": "認識大自然同天氣",
                "sort_order": 4
            },
            {
                "name": "Family",
                "name_cantonese": "家庭",
                "icon": "👨‍👩‍👧",
                "color": "bg-lavender",
                "description": "Learn about family members",
                "description_cantonese": "認識家庭成員",
                "sort_order": 5
            },
            {
                "name": "Transportation",
                "name_cantonese": "交通工具",
                "icon": "🚗",
                "color": "bg-ocean",
                "description": "Learn about vehicles and transportation",
                "description_cantonese": "認識交通工具",
                "sort_order": 6
            },
            {
                "name": "Body Parts",
                "name_cantonese": "身體部位",
                "icon": "👋",
                "color": "bg-peach",
                "description": "Learn about body parts",
                "description_cantonese": "認識身體部位",
                "sort_order": 7
            },
            {
                "name": "Places",
                "name_cantonese": "地方",
                "icon": "🏠",
                "color": "bg-rose",
                "description": "Learn about different places",
                "description_cantonese": "認識唔同嘅地方",
                "sort_order": 8
            },
            {
                "name": "Actions",
                "name_cantonese": "動作",
                "icon": "🏃",
                "color": "bg-amber",
                "description": "Learn about different actions and verbs",
                "description_cantonese": "認識唔同嘅動作",
                "sort_order": 9
            },
            {
                "name": "Numbers",
                "name_cantonese": "數字",
                "icon": "🔢",
                "color": "bg-indigo",
                "description": "Learn to count and use numbers",
                "description_cantonese": "學習數數字",
                "sort_order": 10
            },
            {
                "name": "Shapes",
                "name_cantonese": "形狀",
                "icon": "⭐",
                "color": "bg-purple",
                "description": "Learn about different shapes",
                "description_cantonese": "認識唔同嘅形狀",
                "sort_order": 11
            },
            {
                "name": "Clothing",
                "name_cantonese": "衣服",
                "icon": "👕",
                "color": "bg-pink",
                "description": "Learn about clothes and accessories",
                "description_cantonese": "認識衣服同飾物",
                "sort_order": 12
            },
        ]
        
        categories = {}
        for cat_data in categories_data:
            result = await db.execute(select(Category).where(Category.name == cat_data["name"]))
            category = result.scalars().first()
            
            if category:
                # Update existing category
                for key, value in cat_data.items():
                    if key not in ["name"]:  # Don't update the name
                        setattr(category, key, value)
                print(f"✓ Updated category: {cat_data['name']} ({cat_data['name_cantonese']})")
            else:
                # Create new category
                category = Category(id=str(uuid.uuid4()), **cat_data)
                db.add(category)
                print(f"✓ Created category: {cat_data['name']} ({cat_data['name_cantonese']})")
            
            categories[cat_data["name"]] = category
        
        await db.commit()
        print(f"\n✅ Processed {len(categories)} categories\n")
        
        # ========== VOCABULARY WORDS ==========
        print("📝 Creating vocabulary words with comprehensive data...\n")
        
        words_data = [
            # ========== ANIMALS (10 words) ==========
            {
                "word": "Cat",
                "word_cantonese": "貓",
                "category": "Animals",
                "pronunciation": "kat",
                "jyutping": "maau1",
                "difficulty": "EASY",
                "definition": "A small furry pet that says meow",
                "definition_cantonese": "一種毛茸茸嘅小寵物，會喵喵叫",
                "example": "I see a cat!",
                "example_cantonese": "我見到一隻貓！",
                "image_url": "🐱",
                "physical_action": "Move hands like cat paws and say 'meow'",
                "contexts": ["pets", "home", "animals"],
                "related_words": []  # Will be linked after creation
            },
            {
                "word": "Dog",
                "word_cantonese": "狗",
                "category": "Animals",
                "pronunciation": "dawg",
                "jyutping": "gau2",
                "difficulty": "EASY",
                "definition": "A friendly pet that says woof",
                "definition_cantonese": "一種友善嘅寵物，會汪汪叫",
                "example": "The dog is running!",
                "example_cantonese": "隻狗喺度跑緊！",
                "image_url": "🐶",
                "physical_action": "Pant like a dog and wag your 'tail'",
                "contexts": ["pets", "home", "animals", "park"],
                "related_words": []
            },
            {
                "word": "Elephant",
                "word_cantonese": "大象",
                "category": "Animals",
                "pronunciation": "el-uh-fuhnt",
                "jyutping": "daai6 zoeng6",
                "difficulty": "MEDIUM",
                "definition": "A very large gray animal with a long trunk",
                "definition_cantonese": "一種好大隻、灰色、有長鼻嘅動物",
                "example": "The elephant is so big!",
                "example_cantonese": "大象好大隻！",
                "image_url": "🐘",
                "physical_action": "Use your arm as a trunk and stomp like an elephant",
                "contexts": ["zoo", "animals", "wild"],
                "related_words": []
            },
            {
                "word": "Lion",
                "word_cantonese": "獅子",
                "category": "Animals",
                "pronunciation": "lahy-uhn",
                "jyutping": "si1 zi2",
                "difficulty": "MEDIUM",
                "definition": "A big cat with a mane that roars",
                "definition_cantonese": "一種大貓，有鬃毛，會吼叫",
                "example": "The lion roars loudly!",
                "example_cantonese": "獅子大聲咁吼！",
                "image_url": "🦁",
                "physical_action": "Make a roaring sound and pretend to have a mane",
                "contexts": ["zoo", "animals", "wild", "jungle"],
                "related_words": []
            },
            {
                "word": "Butterfly",
                "word_cantonese": "蝴蝶",
                "category": "Animals",
                "pronunciation": "buht-er-flahy",
                "jyutping": "wu4 dip6",
                "difficulty": "HARD",
                "definition": "A colorful insect with beautiful wings",
                "definition_cantonese": "一種色彩繽紛、有靚翼嘅昆蟲",
                "example": "The butterfly flies in the garden!",
                "example_cantonese": "蝴蝶喺花園飛緊！",
                "image_url": "🦋",
                "physical_action": "Flap arms gently like butterfly wings",
                "contexts": ["garden", "nature", "insects", "flowers"],
                "related_words": []
            },
            {
                "word": "Fish",
                "word_cantonese": "魚",
                "category": "Animals",
                "pronunciation": "fish",
                "jyutping": "jyu4",
                "difficulty": "EASY",
                "definition": "An animal that lives in water",
                "definition_cantonese": "一種住喺水入面嘅動物",
                "example": "The fish swims in the water!",
                "example_cantonese": "魚喺水入面游緊！",
                "image_url": "🐟",
                "physical_action": "Move your hands like swimming fish",
                "contexts": ["water", "ocean", "pets", "food"],
                "related_words": []
            },
            {
                "word": "Bird",
                "word_cantonese": "雀仔",
                "category": "Animals",
                "pronunciation": "burd",
                "jyutping": "zoek3 zai2",
                "difficulty": "EASY",
                "definition": "An animal with wings that can fly",
                "definition_cantonese": "一種有翼、識飛嘅動物",
                "example": "The bird is singing!",
                "example_cantonese": "雀仔喺度唱歌！",
                "image_url": "🐦",
                "physical_action": "Flap arms like wings and chirp",
                "contexts": ["sky", "nature", "trees", "morning"],
                "related_words": []
            },
            {
                "word": "Rabbit",
                "word_cantonese": "兔仔",
                "category": "Animals",
                "pronunciation": "rab-it",
                "jyutping": "tou3 zai2",
                "difficulty": "EASY",
                "definition": "A soft furry animal with long ears that hops",
                "definition_cantonese": "一種毛茸茸、有長耳仔、識跳嘅動物",
                "example": "The rabbit hops in the garden!",
                "example_cantonese": "兔仔喺花園跳緊！",
                "image_url": "🐰",
                "physical_action": "Hop like a bunny and hold hands up like ears",
                "contexts": ["garden", "pets", "animals", "farm"],
                "related_words": []
            },
            {
                "word": "Monkey",
                "word_cantonese": "猴子",
                "category": "Animals",
                "pronunciation": "muhng-kee",
                "jyutping": "hau4 zi2",
                "difficulty": "MEDIUM",
                "definition": "A playful animal that swings in trees",
                "definition_cantonese": "一種好頑皮、喺樹上盪嚟盪去嘅動物",
                "example": "The monkey eats a banana!",
                "example_cantonese": "猴子食緊香蕉！",
                "image_url": "🐵",
                "physical_action": "Scratch under arms and make monkey sounds",
                "contexts": ["zoo", "jungle", "trees", "wild"],
                "related_words": []
            },
            {
                "word": "Turtle",
                "word_cantonese": "龜",
                "category": "Animals",
                "pronunciation": "tur-tl",
                "jyutping": "gwai1",
                "difficulty": "MEDIUM",
                "definition": "A slow animal with a hard shell",
                "definition_cantonese": "一種慢吞吞、有硬殼嘅動物",
                "example": "The turtle walks slowly!",
                "example_cantonese": "龜行得好慢！",
                "image_url": "🐢",
                "physical_action": "Walk very slowly and pretend to have a shell",
                "contexts": ["water", "beach", "pets", "slow"],
                "related_words": []
            },
            
            # ========== FOOD (12 words) ==========
            {
                "word": "Apple",
                "word_cantonese": "蘋果",
                "category": "Food",
                "pronunciation": "ap-uhl",
                "jyutping": "ping4 gwo2",
                "difficulty": "EASY",
                "definition": "A round red or green fruit",
                "definition_cantonese": "一種圓形、紅色或者綠色嘅生果",
                "example": "I eat an apple!",
                "example_cantonese": "我食蘋果！",
                "image_url": "🍎",
                "physical_action": "Pretend to take a big bite of an apple",
                "contexts": ["fruit", "healthy", "snack", "lunch"],
                "related_words": []
            },
            {
                "word": "Banana",
                "word_cantonese": "香蕉",
                "category": "Food",
                "pronunciation": "buh-nan-uh",
                "jyutping": "hoeng1 ziu1",
                "difficulty": "EASY",
                "definition": "A long yellow fruit that you peel",
                "definition_cantonese": "一種長形、黃色、要剝皮嘅生果",
                "example": "The banana is yellow!",
                "example_cantonese": "香蕉係黃色嘅！",
                "image_url": "🍌",
                "physical_action": "Pretend to peel and eat a banana",
                "contexts": ["fruit", "snack", "healthy", "yellow"],
                "related_words": []
            },
            {
                "word": "Rice",
                "word_cantonese": "飯",
                "category": "Food",
                "pronunciation": "rahys",
                "jyutping": "faan6",
                "difficulty": "EASY",
                "definition": "A common food we eat every day",
                "definition_cantonese": "我哋日日都食嘅食物",
                "example": "I eat rice for dinner!",
                "example_cantonese": "我晚餐食飯！",
                "image_url": "🍚",
                "physical_action": "Pretend to scoop and eat rice with chopsticks",
                "contexts": ["meal", "dinner", "lunch", "daily"],
                "related_words": []
            },
            {
                "word": "Noodles",
                "word_cantonese": "麵",
                "category": "Food",
                "pronunciation": "noo-dlz",
                "jyutping": "min6",
                "difficulty": "EASY",
                "definition": "Long thin food made from flour",
                "definition_cantonese": "用麵粉整成嘅長條食物",
                "example": "I love eating noodles!",
                "example_cantonese": "我好鍾意食麵！",
                "image_url": "🍜",
                "physical_action": "Pretend to slurp noodles",
                "contexts": ["meal", "dinner", "lunch", "soup"],
                "related_words": []
            },
            {
                "word": "Egg",
                "word_cantonese": "雞蛋",
                "category": "Food",
                "pronunciation": "eg",
                "jyutping": "gai1 daan6",
                "difficulty": "EASY",
                "definition": "A round food that comes from chickens",
                "definition_cantonese": "雞生出嚟嘅圓形食物",
                "example": "I eat eggs for breakfast!",
                "example_cantonese": "我早餐食雞蛋！",
                "image_url": "🥚",
                "physical_action": "Pretend to crack and cook an egg",
                "contexts": ["breakfast", "protein", "cooking"],
                "related_words": []
            },
            {
                "word": "Milk",
                "word_cantonese": "奶",
                "category": "Food",
                "pronunciation": "milk",
                "jyutping": "naai5",
                "difficulty": "EASY",
                "definition": "A white drink that's good for you",
                "definition_cantonese": "一種白色、有益嘅飲品",
                "example": "I drink milk every day!",
                "example_cantonese": "我日日都飲奶！",
                "image_url": "🥛",
                "physical_action": "Pretend to drink from a glass",
                "contexts": ["drink", "breakfast", "healthy", "white"],
                "related_words": []
            },
            {
                "word": "Bread",
                "word_cantonese": "麵包",
                "category": "Food",
                "pronunciation": "bred",
                "jyutping": "min6 baau1",
                "difficulty": "EASY",
                "definition": "Soft food made from flour that you can toast",
                "definition_cantonese": "用麵粉整成嘅軟身食物，可以烘",
                "example": "I eat bread with butter!",
                "example_cantonese": "我食麵包加牛油！",
                "image_url": "🍞",
                "physical_action": "Pretend to tear and eat bread",
                "contexts": ["breakfast", "sandwich", "toast"],
                "related_words": []
            },
            {
                "word": "Water",
                "word_cantonese": "水",
                "category": "Food",
                "pronunciation": "waw-ter",
                "jyutping": "seoi2",
                "difficulty": "EASY",
                "definition": "Clear drink that we need every day",
                "definition_cantonese": "透明嘅飲品，我哋日日都需要飲",
                "example": "I drink water when I'm thirsty!",
                "example_cantonese": "我口渴就飲水！",
                "image_url": "💧",
                "physical_action": "Pretend to pour and drink water",
                "contexts": ["drink", "healthy", "daily", "thirsty"],
                "related_words": []
            },
            {
                "word": "Orange",
                "word_cantonese": "橙",
                "category": "Food",
                "pronunciation": "or-inj",
                "jyutping": "caang2",
                "difficulty": "MEDIUM",
                "definition": "A round orange fruit with vitamin C",
                "definition_cantonese": "一種圓形、橙色、有維他命C嘅生果",
                "example": "I peel an orange!",
                "example_cantonese": "我剝緊橙！",
                "image_url": "🍊",
                "physical_action": "Pretend to peel an orange",
                "contexts": ["fruit", "healthy", "snack", "juice"],
                "related_words": []
            },
            {
                "word": "Carrot",
                "word_cantonese": "紅蘿蔔",
                "category": "Food",
                "pronunciation": "kar-uht",
                "jyutping": "hung4 lo4 baak6",
                "difficulty": "MEDIUM",
                "definition": "A long orange vegetable that rabbits love",
                "definition_cantonese": "一種長形、橙色、兔仔好鍾意食嘅菜",
                "example": "Rabbits eat carrots!",
                "example_cantonese": "兔仔食紅蘿蔔！",
                "image_url": "🥕",
                "physical_action": "Pretend to munch a carrot like a rabbit",
                "contexts": ["vegetable", "healthy", "orange", "crunchy"],
                "related_words": []
            },
            {
                "word": "Pizza",
                "word_cantonese": "薄餅",
                "category": "Food",
                "pronunciation": "peet-suh",
                "jyutping": "bok6 beng2",
                "difficulty": "EASY",
                "definition": "A round flat food with cheese and toppings",
                "definition_cantonese": "一種圓扁形、有芝士同配料嘅食物",
                "example": "I love pizza for dinner!",
                "example_cantonese": "我好鍾意晚餐食薄餅！",
                "image_url": "🍕",
                "physical_action": "Pretend to hold and eat a slice of pizza",
                "contexts": ["meal", "cheese", "dinner", "party"],
                "related_words": []
            },
            {
                "word": "Ice Cream",
                "word_cantonese": "雪糕",
                "category": "Food",
                "pronunciation": "ahys kreem",
                "jyutping": "syut3 gou1",
                "difficulty": "EASY",
                "definition": "A cold sweet treat that melts",
                "definition_cantonese": "一種凍嘅、甜嘅、會溶嘅食物",
                "example": "I eat ice cream in summer!",
                "example_cantonese": "我夏天食雪糕！",
                "image_url": "🍦",
                "physical_action": "Pretend to lick an ice cream cone",
                "contexts": ["dessert", "sweet", "cold", "treat"],
                "related_words": []
            },
            
            # ========== COLORS (8 words) ==========
            {
                "word": "Red",
                "word_cantonese": "紅色",
                "category": "Colors",
                "pronunciation": "red",
                "jyutping": "hung4 sik1",
                "difficulty": "EASY",
                "definition": "The color of apples and fire trucks",
                "definition_cantonese": "蘋果同消防車嘅顏色",
                "example": "The apple is red!",
                "example_cantonese": "蘋果係紅色嘅！",
                "image_url": "🔴",
                "physical_action": "Point to something red",
                "contexts": ["color", "apple", "fire", "stop"],
                "related_words": []
            },
            {
                "word": "Blue",
                "word_cantonese": "藍色",
                "category": "Colors",
                "pronunciation": "bloo",
                "jyutping": "laam4 sik1",
                "difficulty": "EASY",
                "definition": "The color of the sky and ocean",
                "definition_cantonese": "天空同海洋嘅顏色",
                "example": "The sky is blue!",
                "example_cantonese": "天空係藍色嘅！",
                "image_url": "🔵",
                "physical_action": "Point to the sky",
                "contexts": ["color", "sky", "ocean", "water"],
                "related_words": []
            },
            {
                "word": "Yellow",
                "word_cantonese": "黃色",
                "category": "Colors",
                "pronunciation": "yel-oh",
                "jyutping": "wong4 sik1",
                "difficulty": "EASY",
                "definition": "The color of the sun and bananas",
                "definition_cantonese": "太陽同香蕉嘅顏色",
                "example": "The banana is yellow!",
                "example_cantonese": "香蕉係黃色嘅！",
                "image_url": "🟡",
                "physical_action": "Make a circle like the sun",
                "contexts": ["color", "sun", "banana", "bright"],
                "related_words": []
            },
            {
                "word": "Green",
                "word_cantonese": "綠色",
                "category": "Colors",
                "pronunciation": "green",
                "jyutping": "luk6 sik1",
                "difficulty": "EASY",
                "definition": "The color of grass and leaves",
                "definition_cantonese": "草同樹葉嘅顏色",
                "example": "The grass is green!",
                "example_cantonese": "草係綠色嘅！",
                "image_url": "🟢",
                "physical_action": "Point to grass or leaves",
                "contexts": ["color", "nature", "grass", "go"],
                "related_words": []
            },
            {
                "word": "Orange",
                "word_cantonese": "橙色",
                "category": "Colors",
                "pronunciation": "or-inj",
                "jyutping": "caang2 sik1",
                "difficulty": "MEDIUM",
                "definition": "The color of oranges and carrots",
                "definition_cantonese": "橙同紅蘿蔔嘅顏色",
                "example": "The carrot is orange!",
                "example_cantonese": "紅蘿蔔係橙色嘅！",
                "image_url": "🟠",
                "physical_action": "Hold up an orange or point to something orange",
                "contexts": ["color", "fruit", "sunset"],
                "related_words": []
            },
            {
                "word": "Purple",
                "word_cantonese": "紫色",
                "category": "Colors",
                "pronunciation": "pur-puhl",
                "jyutping": "zi2 sik1",
                "difficulty": "MEDIUM",
                "definition": "The color of grapes and violets",
                "definition_cantonese": "提子同紫羅蘭嘅顏色",
                "example": "The flower is purple!",
                "example_cantonese": "花係紫色嘅！",
                "image_url": "🟣",
                "physical_action": "Point to something purple",
                "contexts": ["color", "flower", "grape"],
                "related_words": []
            },
            {
                "word": "Pink",
                "word_cantonese": "粉紅色",
                "category": "Colors",
                "pronunciation": "pingk",
                "jyutping": "fan2 hung4 sik1",
                "difficulty": "MEDIUM",
                "definition": "A light red color like roses",
                "definition_cantonese": "淡紅色，好似玫瑰咁",
                "example": "The flower is pink!",
                "example_cantonese": "花係粉紅色嘅！",
                "image_url": "🌸",
                "physical_action": "Point to something pink",
                "contexts": ["color", "flower", "light"],
                "related_words": []
            },
            {
                "word": "Black",
                "word_cantonese": "黑色",
                "category": "Colors",
                "pronunciation": "blak",
                "jyutping": "hak1 sik1",
                "difficulty": "EASY",
                "definition": "The color of night and darkness",
                "definition_cantonese": "夜晚同黑暗嘅顏色",
                "example": "The night is black!",
                "example_cantonese": "夜晚係黑色嘅！",
                "image_url": "⚫",
                "physical_action": "Close eyes to show darkness",
                "contexts": ["color", "night", "dark"],
                "related_words": []
            },
            
            # ========== NATURE (10 words) ==========
            {
                "word": "Tree",
                "word_cantonese": "樹",
                "category": "Nature",
                "pronunciation": "tree",
                "jyutping": "syu6",
                "difficulty": "EASY",
                "definition": "A tall plant with branches and leaves",
                "definition_cantonese": "一種高大、有樹枝同樹葉嘅植物",
                "example": "The tree is so tall!",
                "example_cantonese": "樹好高！",
                "image_url": "🌳",
                "physical_action": "Stand tall with arms up like tree branches",
                "contexts": ["nature", "park", "forest", "green"],
                "related_words": []
            },
            {
                "word": "Flower",
                "word_cantonese": "花",
                "category": "Nature",
                "pronunciation": "flou-er",
                "jyutping": "faa1",
                "difficulty": "EASY",
                "definition": "A pretty plant with colorful petals",
                "definition_cantonese": "一種靚嘅植物，有色彩繽紛嘅花瓣",
                "example": "The flower smells nice!",
                "example_cantonese": "花好香！",
                "image_url": "🌸",
                "physical_action": "Pretend to smell a flower",
                "contexts": ["nature", "garden", "pretty", "smell"],
                "related_words": []
            },
            {
                "word": "Sun",
                "word_cantonese": "太陽",
                "category": "Nature",
                "pronunciation": "suhn",
                "jyutping": "taai3 joeng4",
                "difficulty": "EASY",
                "definition": "The bright light in the sky during the day",
                "definition_cantonese": "日頭天空入面嘅光",
                "example": "The sun is bright!",
                "example_cantonese": "太陽好光！",
                "image_url": "☀️",
                "physical_action": "Make a big circle with arms above head",
                "contexts": ["weather", "day", "bright", "hot"],
                "related_words": []
            },
            {
                "word": "Rain",
                "word_cantonese": "雨",
                "category": "Nature",
                "pronunciation": "reyn",
                "jyutping": "jyu5",
                "difficulty": "EASY",
                "definition": "Water that falls from the clouds",
                "definition_cantonese": "從雲落落嚟嘅水",
                "example": "It's raining today!",
                "example_cantonese": "今日落緊雨！",
                "image_url": "🌧️",
                "physical_action": "Wiggle fingers downward like falling rain",
                "contexts": ["weather", "water", "wet", "umbrella"],
                "related_words": []
            },
            {
                "word": "Moon",
                "word_cantonese": "月亮",
                "category": "Nature",
                "pronunciation": "moon",
                "jyutping": "jyut6 loeng6",
                "difficulty": "EASY",
                "definition": "The bright light in the night sky",
                "definition_cantonese": "夜晚天空嘅光",
                "example": "I see the moon at night!",
                "example_cantonese": "我夜晚見到月亮！",
                "image_url": "🌙",
                "physical_action": "Make a crescent shape with arms",
                "contexts": ["night", "sky", "stars", "bedtime"],
                "related_words": []
            },
            {
                "word": "Star",
                "word_cantonese": "星星",
                "category": "Nature",
                "pronunciation": "stahr",
                "jyutping": "sing1 sing1",
                "difficulty": "EASY",
                "definition": "Tiny lights that twinkle in the night sky",
                "definition_cantonese": "夜晚天空閃閃發光嘅細小光點",
                "example": "I see many stars!",
                "example_cantonese": "我見到好多星星！",
                "image_url": "⭐",
                "physical_action": "Open and close hands like twinkling stars",
                "contexts": ["night", "sky", "bright", "wish"],
                "related_words": []
            },
            {
                "word": "Cloud",
                "word_cantonese": "雲",
                "category": "Nature",
                "pronunciation": "kloud",
                "jyutping": "wan4",
                "difficulty": "MEDIUM",
                "definition": "White fluffy things floating in the sky",
                "definition_cantonese": "天空飄浮嘅白色軟綿綿嘢",
                "example": "The clouds are white!",
                "example_cantonese": "雲係白色嘅！",
                "image_url": "☁️",
                "physical_action": "Make a round fluffy shape with hands",
                "contexts": ["sky", "weather", "soft", "white"],
                "related_words": []
            },
            {
                "word": "Wind",
                "word_cantonese": "風",
                "category": "Nature",
                "pronunciation": "wind",
                "jyutping": "fung1",
                "difficulty": "MEDIUM",
                "definition": "Moving air that you can feel but not see",
                "definition_cantonese": "移動緊嘅空氣，你感覺到但睇唔到",
                "example": "The wind blows my hair!",
                "example_cantonese": "風吹起我嘅頭髮！",
                "image_url": "💨",
                "physical_action": "Blow air and wave hands",
                "contexts": ["weather", "air", "blow", "feel"],
                "related_words": []
            },
            {
                "word": "Grass",
                "word_cantonese": "草",
                "category": "Nature",
                "pronunciation": "gras",
                "jyutping": "cou2",
                "difficulty": "EASY",
                "definition": "Short green plants on the ground",
                "definition_cantonese": "地上嘅綠色短植物",
                "example": "I sit on the grass!",
                "example_cantonese": "我坐喺草度！",
                "image_url": "🌱",
                "physical_action": "Pat the ground gently",
                "contexts": ["park", "green", "ground", "soft"],
                "related_words": []
            },
            {
                "word": "Mountain",
                "word_cantonese": "山",
                "category": "Nature",
                "pronunciation": "moun-tn",
                "jyutping": "saan1",
                "difficulty": "MEDIUM",
                "definition": "A very tall hill with rocks",
                "definition_cantonese": "一座好高、有石頭嘅山丘",
                "example": "The mountain is very high!",
                "example_cantonese": "山好高！",
                "image_url": "⛰️",
                "physical_action": "Make a peak shape with hands",
                "contexts": ["nature", "high", "climb", "hike"],
                "related_words": []
            },
            
            # ========== FAMILY (8 words) ==========
            {
                "word": "Mom",
                "word_cantonese": "媽媽",
                "category": "Family",
                "pronunciation": "mom",
                "jyutping": "maa1 maa1",
                "difficulty": "EASY",
                "definition": "Your mother who takes care of you",
                "definition_cantonese": "你嘅母親，照顧你嘅人",
                "example": "I love my mom!",
                "example_cantonese": "我好愛媽媽！",
                "image_url": "👩",
                "physical_action": "Give a big hug",
                "contexts": ["family", "love", "home", "parent"],
                "related_words": []
            },
            {
                "word": "Dad",
                "word_cantonese": "爸爸",
                "category": "Family",
                "pronunciation": "dad",
                "jyutping": "baa1 baa1",
                "difficulty": "EASY",
                "definition": "Your father who takes care of you",
                "definition_cantonese": "你嘅父親，照顧你嘅人",
                "example": "Dad plays with me!",
                "example_cantonese": "爸爸同我玩！",
                "image_url": "👨",
                "physical_action": "Give a big hug",
                "contexts": ["family", "love", "home", "parent"],
                "related_words": []
            },
            {
                "word": "Sister",
                "word_cantonese": "姐姐",
                "category": "Family",
                "pronunciation": "sis-ter",
                "jyutping": "ze2 ze2",
                "difficulty": "EASY",
                "definition": "A girl who shares your parents",
                "definition_cantonese": "同你有相同父母嘅女孩",
                "example": "My sister is nice!",
                "example_cantonese": "我姐姐好好！",
                "image_url": "👧",
                "physical_action": "Hold hands like siblings",
                "contexts": ["family", "sibling", "girl", "share"],
                "related_words": []
            },
            {
                "word": "Brother",
                "word_cantonese": "哥哥",
                "category": "Family",
                "pronunciation": "bruhth-er",
                "jyutping": "go1 go1",
                "difficulty": "EASY",
                "definition": "A boy who shares your parents",
                "definition_cantonese": "同你有相同父母嘅男孩",
                "example": "My brother plays with me!",
                "example_cantonese": "我哥哥同我玩！",
                "image_url": "👦",
                "physical_action": "Pretend to play together",
                "contexts": ["family", "sibling", "boy", "play"],
                "related_words": []
            },
            {
                "word": "Grandma",
                "word_cantonese": "嫲嫲",
                "category": "Family",
                "pronunciation": "gran-mah",
                "jyutping": "maa4 maa4",
                "difficulty": "MEDIUM",
                "definition": "Your parent's mother",
                "definition_cantonese": "你父母嘅媽媽",
                "example": "Grandma tells me stories!",
                "example_cantonese": "嫲嫲講故事俾我聽！",
                "image_url": "👵",
                "physical_action": "Pretend to listen to a story",
                "contexts": ["family", "grandparent", "old", "love"],
                "related_words": []
            },
            {
                "word": "Grandpa",
                "word_cantonese": "爺爺",
                "category": "Family",
                "pronunciation": "gran-pah",
                "jyutping": "je4 je4",
                "difficulty": "MEDIUM",
                "definition": "Your parent's father",
                "definition_cantonese": "你父母嘅爸爸",
                "example": "Grandpa is funny!",
                "example_cantonese": "爺爺好搞笑！",
                "image_url": "👴",
                "physical_action": "Laugh and smile",
                "contexts": ["family", "grandparent", "old", "fun"],
                "related_words": []
            },
            {
                "word": "Baby",
                "word_cantonese": "BB",
                "category": "Family",
                "pronunciation": "bey-bee",
                "jyutping": "bi1 bi1",
                "difficulty": "EASY",
                "definition": "A very young child",
                "definition_cantonese": "好細嘅小朋友",
                "example": "The baby is sleeping!",
                "example_cantonese": "BB瞓緊覺！",
                "image_url": "👶",
                "physical_action": "Rock arms like holding a baby",
                "contexts": ["family", "young", "small", "cute"],
                "related_words": []
            },
            {
                "word": "Friend",
                "word_cantonese": "朋友",
                "category": "Family",
                "pronunciation": "frend",
                "jyutping": "pang4 jau5",
                "difficulty": "EASY",
                "definition": "Someone you like to play with",
                "definition_cantonese": "你鍾意同佢玩嘅人",
                "example": "I play with my friend!",
                "example_cantonese": "我同朋友玩！",
                "image_url": "👫",
                "physical_action": "Hold hands and smile",
                "contexts": ["play", "school", "happy", "share"],
                "related_words": []
            },
            
            # ========== TRANSPORTATION (7 words) ==========
            {
                "word": "Car",
                "word_cantonese": "車",
                "category": "Transportation",
                "pronunciation": "kahr",
                "jyutping": "ce1",
                "difficulty": "EASY",
                "definition": "A vehicle with four wheels",
                "definition_cantonese": "一種有四個轆嘅交通工具",
                "example": "The car goes fast!",
                "example_cantonese": "車行得好快！",
                "image_url": "🚗",
                "physical_action": "Pretend to drive a steering wheel",
                "contexts": ["vehicle", "road", "fast", "drive"],
                "related_words": []
            },
            {
                "word": "Bus",
                "word_cantonese": "巴士",
                "category": "Transportation",
                "pronunciation": "buhs",
                "jyutping": "baa1 si6",
                "difficulty": "EASY",
                "definition": "A big vehicle that carries many people",
                "definition_cantonese": "一種大型、載好多人嘅交通工具",
                "example": "I go to school by bus!",
                "example_cantonese": "我搭巴士返學！",
                "image_url": "🚌",
                "physical_action": "Pretend to pay and sit on a bus",
                "contexts": ["vehicle", "school", "big", "passengers"],
                "related_words": []
            },
            {
                "word": "Airplane",
                "word_cantonese": "飛機",
                "category": "Transportation",
                "pronunciation": "air-pleyn",
                "jyutping": "fei1 gei1",
                "difficulty": "MEDIUM",
                "definition": "A vehicle that flies in the sky",
                "definition_cantonese": "一種喺天空飛嘅交通工具",
                "example": "The airplane flies high!",
                "example_cantonese": "飛機飛得好高！",
                "image_url": "✈️",
                "physical_action": "Spread arms like wings and fly",
                "contexts": ["vehicle", "sky", "travel", "high"],
                "related_words": []
            },
            {
                "word": "Train",
                "word_cantonese": "火車",
                "category": "Transportation",
                "pronunciation": "treyn",
                "jyutping": "fo2 ce1",
                "difficulty": "MEDIUM",
                "definition": "A long vehicle that runs on tracks",
                "definition_cantonese": "一種長形、喺路軌上行駛嘅交通工具",
                "example": "The train goes choo-choo!",
                "example_cantonese": "火車嘟嘟響！",
                "image_url": "🚂",
                "physical_action": "Move arms like train wheels and say 'choo-choo'",
                "contexts": ["vehicle", "tracks", "long", "travel"],
                "related_words": []
            },
            {
                "word": "Bicycle",
                "word_cantonese": "單車",
                "category": "Transportation",
                "pronunciation": "bahy-si-kuhl",
                "jyutping": "daan1 ce1",
                "difficulty": "MEDIUM",
                "definition": "A vehicle with two wheels you pedal",
                "definition_cantonese": "一種有兩個轆、要踩嘅交通工具",
                "example": "I ride my bicycle!",
                "example_cantonese": "我踩單車！",
                "image_url": "🚲",
                "physical_action": "Pretend to pedal a bicycle",
                "contexts": ["vehicle", "exercise", "pedal", "fun"],
                "related_words": []
            },
            {
                "word": "Boat",
                "word_cantonese": "船",
                "category": "Transportation",
                "pronunciation": "boht",
                "jyutping": "syun4",
                "difficulty": "MEDIUM",
                "definition": "A vehicle that floats on water",
                "definition_cantonese": "一種喺水上浮嘅交通工具",
                "example": "The boat sails on water!",
                "example_cantonese": "船喺水上航行！",
                "image_url": "⛵",
                "physical_action": "Rock side to side like on a boat",
                "contexts": ["vehicle", "water", "sail", "float"],
                "related_words": []
            },
            {
                "word": "Helicopter",
                "word_cantonese": "直升機",
                "category": "Transportation",
                "pronunciation": "hel-i-kop-ter",
                "jyutping": "zik6 sing1 gei1",
                "difficulty": "HARD",
                "definition": "A flying vehicle with spinning blades on top",
                "definition_cantonese": "一種頂部有旋轉葉片嘅飛行交通工具",
                "example": "The helicopter flies up!",
                "example_cantonese": "直升機向上飛！",
                "image_url": "🚁",
                "physical_action": "Spin arms above head like helicopter blades",
                "contexts": ["vehicle", "sky", "rescue", "spin"],
                "related_words": []
            },
            
            # ========== BODY PARTS (10 words) ==========
            {
                "word": "Eye",
                "word_cantonese": "眼",
                "category": "Body Parts",
                "pronunciation": "ahy",
                "jyutping": "ngaan5",
                "difficulty": "EASY",
                "definition": "What you use to see",
                "definition_cantonese": "你用嚟睇嘢嘅器官",
                "example": "I see with my eyes!",
                "example_cantonese": "我用眼睇嘢！",
                "image_url": "👁️",
                "physical_action": "Point to your eyes",
                "contexts": ["body", "see", "face", "vision"],
                "related_words": []
            },
            {
                "word": "Ear",
                "word_cantonese": "耳仔",
                "category": "Body Parts",
                "pronunciation": "eer",
                "jyutping": "ji5 zai2",
                "difficulty": "EASY",
                "definition": "What you use to hear",
                "definition_cantonese": "你用嚟聽嘢嘅器官",
                "example": "I hear with my ears!",
                "example_cantonese": "我用耳仔聽嘢！",
                "image_url": "👂",
                "physical_action": "Cup your hand behind your ear",
                "contexts": ["body", "hear", "listen", "sound"],
                "related_words": []
            },
            {
                "word": "Nose",
                "word_cantonese": "鼻",
                "category": "Body Parts",
                "pronunciation": "nohz",
                "jyutping": "bei6",
                "difficulty": "EASY",
                "definition": "What you use to smell",
                "definition_cantonese": "你用嚟聞嘢嘅器官",
                "example": "I smell with my nose!",
                "example_cantonese": "我用鼻聞嘢！",
                "image_url": "👃",
                "physical_action": "Point to your nose",
                "contexts": ["body", "smell", "face", "breathe"],
                "related_words": []
            },
            {
                "word": "Mouth",
                "word_cantonese": "嘴",
                "category": "Body Parts",
                "pronunciation": "mouth",
                "jyutping": "zeoi2",
                "difficulty": "EASY",
                "definition": "What you use to eat and talk",
                "definition_cantonese": "你用嚟食嘢同講嘢嘅器官",
                "example": "I eat with my mouth!",
                "example_cantonese": "我用嘴食嘢！",
                "image_url": "👄",
                "physical_action": "Point to your mouth",
                "contexts": ["body", "eat", "talk", "face"],
                "related_words": []
            },
            {
                "word": "Hand",
                "word_cantonese": "手",
                "category": "Body Parts",
                "pronunciation": "hand",
                "jyutping": "sau2",
                "difficulty": "EASY",
                "definition": "What you use to hold and touch things",
                "definition_cantonese": "你用嚟拎嘢同摸嘢嘅器官",
                "example": "I wave my hand!",
                "example_cantonese": "我揮手！",
                "image_url": "✋",
                "physical_action": "Wave your hand",
                "contexts": ["body", "touch", "hold", "wave"],
                "related_words": []
            },
            {
                "word": "Foot",
                "word_cantonese": "腳",
                "category": "Body Parts",
                "pronunciation": "foot",
                "jyutping": "goek3",
                "difficulty": "EASY",
                "definition": "What you use to walk and run",
                "definition_cantonese": "你用嚟行同跑嘅器官",
                "example": "I walk with my feet!",
                "example_cantonese": "我用腳行路！",
                "image_url": "🦶",
                "physical_action": "Stomp your feet",
                "contexts": ["body", "walk", "run", "shoe"],
                "related_words": []
            },
            {
                "word": "Head",
                "word_cantonese": "頭",
                "category": "Body Parts",
                "pronunciation": "hed",
                "jyutping": "tau4",
                "difficulty": "EASY",
                "definition": "The top part of your body where your brain is",
                "definition_cantonese": "你身體最上面、有腦嘅部位",
                "example": "I nod my head!",
                "example_cantonese": "我點頭！",
                "image_url": "🙂",
                "physical_action": "Pat your head gently",
                "contexts": ["body", "brain", "think", "top"],
                "related_words": []
            },
            {
                "word": "Arm",
                "word_cantonese": "手臂",
                "category": "Body Parts",
                "pronunciation": "ahrm",
                "jyutping": "sau2 bei3",
                "difficulty": "MEDIUM",
                "definition": "The part between your shoulder and hand",
                "definition_cantonese": "膊頭同手之間嘅部位",
                "example": "I stretch my arms!",
                "example_cantonese": "我伸展手臂！",
                "image_url": "💪",
                "physical_action": "Stretch arms up high",
                "contexts": ["body", "stretch", "strong", "reach"],
                "related_words": []
            },
            {
                "word": "Leg",
                "word_cantonese": "腿",
                "category": "Body Parts",
                "pronunciation": "leg",
                "jyutping": "teoi2",
                "difficulty": "MEDIUM",
                "definition": "The part between your hip and foot",
                "definition_cantonese": "臀部同腳之間嘅部位",
                "example": "I kick my leg!",
                "example_cantonese": "我踢腿！",
                "image_url": "🦵",
                "physical_action": "Kick your leg gently",
                "contexts": ["body", "walk", "kick", "strong"],
                "related_words": []
            },
            {
                "word": "Hair",
                "word_cantonese": "頭髮",
                "category": "Body Parts",
                "pronunciation": "hair",
                "jyutping": "tau4 faat3",
                "difficulty": "EASY",
                "definition": "What grows on your head",
                "definition_cantonese": "喺你頭上生長嘅嘢",
                "example": "I brush my hair!",
                "example_cantonese": "我梳頭髮！",
                "image_url": "💇",
                "physical_action": "Pretend to brush your hair",
                "contexts": ["body", "head", "brush", "style"],
                "related_words": []
            },
            
            # ========== PLACES (8 words) ==========
            {
                "word": "Home",
                "word_cantonese": "屋企",
                "category": "Places",
                "pronunciation": "hohm",
                "jyutping": "uk1 kei5",
                "difficulty": "EASY",
                "definition": "Where you live with your family",
                "definition_cantonese": "你同家人住嘅地方",
                "example": "I go home after school!",
                "example_cantonese": "我放學返屋企！",
                "image_url": "🏠",
                "physical_action": "Make a roof shape with hands above head",
                "contexts": ["place", "family", "live", "safe"],
                "related_words": []
            },
            {
                "word": "School",
                "word_cantonese": "學校",
                "category": "Places",
                "pronunciation": "skool",
                "jyutping": "hok6 haau6",
                "difficulty": "MEDIUM",
                "definition": "Where you go to learn",
                "definition_cantonese": "你去學嘢嘅地方",
                "example": "I learn at school!",
                "example_cantonese": "我喺學校學嘢！",
                "image_url": "🏫",
                "physical_action": "Pretend to write on a board",
                "contexts": ["place", "learn", "teacher", "friends"],
                "related_words": []
            },
            {
                "word": "Park",
                "word_cantonese": "公園",
                "category": "Places",
                "pronunciation": "pahrk",
                "jyutping": "gung1 jyun4",
                "difficulty": "EASY",
                "definition": "A place with grass and playground",
                "definition_cantonese": "一個有草地同遊樂場嘅地方",
                "example": "I play at the park!",
                "example_cantonese": "我喺公園玩！",
                "image_url": "🏞️",
                "physical_action": "Pretend to swing on swings",
                "contexts": ["place", "play", "outside", "fun"],
                "related_words": []
            },
            {
                "word": "Store",
                "word_cantonese": "商店",
                "category": "Places",
                "pronunciation": "stawr",
                "jyutping": "soeng1 dim3",
                "difficulty": "MEDIUM",
                "definition": "A place where you buy things",
                "definition_cantonese": "你買嘢嘅地方",
                "example": "I buy food at the store!",
                "example_cantonese": "我喺商店買食物！",
                "image_url": "🏪",
                "physical_action": "Pretend to pick items and pay",
                "contexts": ["place", "buy", "shop", "money"],
                "related_words": []
            },
            {
                "word": "Beach",
                "word_cantonese": "沙灘",
                "category": "Places",
                "pronunciation": "beech",
                "jyutping": "saa1 taan1",
                "difficulty": "MEDIUM",
                "definition": "A place with sand near the water",
                "definition_cantonese": "近水、有沙嘅地方",
                "example": "I play at the beach!",
                "example_cantonese": "我喺沙灘玩！",
                "image_url": "🏖️",
                "physical_action": "Pretend to build sandcastles",
                "contexts": ["place", "sand", "water", "summer"],
                "related_words": []
            },
            {
                "word": "Library",
                "word_cantonese": "圖書館",
                "category": "Places",
                "pronunciation": "lahy-brer-ee",
                "jyutping": "tou4 syu1 gun2",
                "difficulty": "HARD",
                "definition": "A quiet place with many books",
                "definition_cantonese": "一個安靜、有好多書嘅地方",
                "example": "I read books at the library!",
                "example_cantonese": "我喺圖書館睇書！",
                "image_url": "📚",
                "physical_action": "Pretend to read a book quietly",
                "contexts": ["place", "books", "quiet", "read"],
                "related_words": []
            },
            {
                "word": "Hospital",
                "word_cantonese": "醫院",
                "category": "Places",
                "pronunciation": "hos-pi-tl",
                "jyutping": "ji1 jyun2",
                "difficulty": "HARD",
                "definition": "A place where doctors help sick people",
                "definition_cantonese": "醫生幫病人嘅地方",
                "example": "The doctor works at the hospital!",
                "example_cantonese": "醫生喺醫院工作！",
                "image_url": "🏥",
                "physical_action": "Pretend to check a heartbeat",
                "contexts": ["place", "doctor", "sick", "help"],
                "related_words": []
            },
            {
                "word": "Restaurant",
                "word_cantonese": "餐廳",
                "category": "Places",
                "pronunciation": "res-ter-ont",
                "jyutping": "caan1 teng1",
                "difficulty": "HARD",
                "definition": "A place where you eat food someone cooks for you",
                "definition_cantonese": "一個你食別人煮嘅食物嘅地方",
                "example": "We eat dinner at a restaurant!",
                "example_cantonese": "我哋喺餐廳食晚餐！",
                "image_url": "🍽️",
                "physical_action": "Pretend to eat with utensils",
                "contexts": ["place", "food", "eat", "family"],
                "related_words": []
            },
            
            # ========== ACTIONS (10 words) ==========
            {
                "word": "Run",
                "word_cantonese": "跑",
                "category": "Actions",
                "pronunciation": "ruhn",
                "jyutping": "paau2",
                "difficulty": "EASY",
                "definition": "To move very fast with your legs",
                "definition_cantonese": "用你嘅腳好快咁移動",
                "example": "I run fast!",
                "example_cantonese": "我跑得好快！",
                "image_url": "🏃",
                "physical_action": "Run in place",
                "contexts": ["action", "fast", "exercise", "play"],
                "related_words": []
            },
            {
                "word": "Jump",
                "word_cantonese": "跳",
                "category": "Actions",
                "pronunciation": "juhmp",
                "jyutping": "tiu3",
                "difficulty": "EASY",
                "definition": "To push yourself off the ground",
                "definition_cantonese": "用力推自己離開地面",
                "example": "I jump high!",
                "example_cantonese": "我跳得好高！",
                "image_url": "🦘",
                "physical_action": "Jump up and down",
                "contexts": ["action", "high", "fun", "play"],
                "related_words": []
            },
            {
                "word": "Walk",
                "word_cantonese": "行",
                "category": "Actions",
                "pronunciation": "wawk",
                "jyutping": "haang4",
                "difficulty": "EASY",
                "definition": "To move by putting one foot in front of the other",
                "definition_cantonese": "一隻腳跟住另一隻腳咁移動",
                "example": "I walk to school!",
                "example_cantonese": "我行路返學！",
                "image_url": "🚶",
                "physical_action": "Walk in place",
                "contexts": ["action", "move", "daily", "go"],
                "related_words": []
            },
            {
                "word": "Eat",
                "word_cantonese": "食",
                "category": "Actions",
                "pronunciation": "eet",
                "jyutping": "sik6",
                "difficulty": "EASY",
                "definition": "To put food in your mouth and swallow",
                "definition_cantonese": "將食物放入口然後吞落肚",
                "example": "I eat my lunch!",
                "example_cantonese": "我食午餐！",
                "image_url": "🍽️",
                "physical_action": "Pretend to eat",
                "contexts": ["action", "food", "meal", "hungry"],
                "related_words": []
            },
            {
                "word": "Sleep",
                "word_cantonese": "瞓覺",
                "category": "Actions",
                "pronunciation": "sleep",
                "jyutping": "fan3 gaau3",
                "difficulty": "EASY",
                "definition": "To close your eyes and rest",
                "definition_cantonese": "閂埋眼休息",
                "example": "I sleep at night!",
                "example_cantonese": "我夜晚瞓覺！",
                "image_url": "😴",
                "physical_action": "Close eyes and put hands together like a pillow",
                "contexts": ["action", "night", "rest", "bed"],
                "related_words": []
            },
            {
                "word": "Sit",
                "word_cantonese": "坐",
                "category": "Actions",
                "pronunciation": "sit",
                "jyutping": "co5",
                "difficulty": "EASY",
                "definition": "To rest on your bottom",
                "definition_cantonese": "用屁股休息",
                "example": "I sit on the chair!",
                "example_cantonese": "我坐喺凳度！",
                "image_url": "💺",
                "physical_action": "Sit down",
                "contexts": ["action", "chair", "rest", "calm"],
                "related_words": []
            },
            {
                "word": "Dance",
                "word_cantonese": "跳舞",
                "category": "Actions",
                "pronunciation": "dans",
                "jyutping": "tiu3 mou5",
                "difficulty": "MEDIUM",
                "definition": "To move your body to music",
                "definition_cantonese": "跟住音樂郁動身體",
                "example": "I love to dance!",
                "example_cantonese": "我好鍾意跳舞！",
                "image_url": "💃",
                "physical_action": "Dance and move to music",
                "contexts": ["action", "music", "fun", "happy"],
                "related_words": []
            },
            {
                "word": "Sing",
                "word_cantonese": "唱歌",
                "category": "Actions",
                "pronunciation": "sing",
                "jyutping": "coeng3 go1",
                "difficulty": "MEDIUM",
                "definition": "To make music with your voice",
                "definition_cantonese": "用聲音製造音樂",
                "example": "I sing a song!",
                "example_cantonese": "我唱緊歌！",
                "image_url": "🎤",
                "physical_action": "Pretend to hold a microphone and sing",
                "contexts": ["action", "music", "happy", "voice"],
                "related_words": []
            },
            {
                "word": "Draw",
                "word_cantonese": "畫畫",
                "category": "Actions",
                "pronunciation": "draw",
                "jyutping": "waak6 waa2",
                "difficulty": "MEDIUM",
                "definition": "To make pictures with crayons or pencils",
                "definition_cantonese": "用蠟筆或鉛筆畫圖畫",
                "example": "I draw a picture!",
                "example_cantonese": "我畫緊圖畫！",
                "image_url": "🎨",
                "physical_action": "Pretend to draw on paper",
                "contexts": ["action", "art", "creative", "fun"],
                "related_words": []
            },
            {
                "word": "Clap",
                "word_cantonese": "拍手",
                "category": "Actions",
                "pronunciation": "klap",
                "jyutping": "paak3 sau2",
                "difficulty": "EASY",
                "definition": "To hit your hands together to make sound",
                "definition_cantonese": "兩隻手拍埋一齊發聲",
                "example": "I clap my hands!",
                "example_cantonese": "我拍手！",
                "image_url": "👏",
                "physical_action": "Clap your hands",
                "contexts": ["action", "sound", "happy", "celebrate"],
                "related_words": []
            },
            
            # ========== NUMBERS (10 words) ==========
            {
                "word": "One",
                "word_cantonese": "一",
                "category": "Numbers",
                "pronunciation": "wuhn",
                "jyutping": "jat1",
                "difficulty": "EASY",
                "definition": "The first number",
                "definition_cantonese": "第一個數字",
                "example": "I have one apple!",
                "example_cantonese": "我有一個蘋果！",
                "image_url": "1️⃣",
                "physical_action": "Hold up one finger",
                "contexts": ["number", "count", "single", "first"],
                "related_words": []
            },
            {
                "word": "Two",
                "word_cantonese": "二",
                "category": "Numbers",
                "pronunciation": "too",
                "jyutping": "ji6",
                "difficulty": "EASY",
                "definition": "The number after one",
                "definition_cantonese": "一之後嘅數字",
                "example": "I have two eyes!",
                "example_cantonese": "我有兩隻眼！",
                "image_url": "2️⃣",
                "physical_action": "Hold up two fingers",
                "contexts": ["number", "count", "pair", "double"],
                "related_words": []
            },
            {
                "word": "Three",
                "word_cantonese": "三",
                "category": "Numbers",
                "pronunciation": "three",
                "jyutping": "saam1",
                "difficulty": "EASY",
                "definition": "The number after two",
                "definition_cantonese": "二之後嘅數字",
                "example": "I am three years old!",
                "example_cantonese": "我三歲！",
                "image_url": "3️⃣",
                "physical_action": "Hold up three fingers",
                "contexts": ["number", "count", "age", "trio"],
                "related_words": []
            },
            {
                "word": "Four",
                "word_cantonese": "四",
                "category": "Numbers",
                "pronunciation": "fawr",
                "jyutping": "sei3",
                "difficulty": "EASY",
                "definition": "The number after three",
                "definition_cantonese": "三之後嘅數字",
                "example": "A car has four wheels!",
                "example_cantonese": "車有四個轆！",
                "image_url": "4️⃣",
                "physical_action": "Hold up four fingers",
                "contexts": ["number", "count", "square", "quad"],
                "related_words": []
            },
            {
                "word": "Five",
                "word_cantonese": "五",
                "category": "Numbers",
                "pronunciation": "fahyv",
                "jyutping": "ng5",
                "difficulty": "EASY",
                "definition": "The number after four",
                "definition_cantonese": "四之後嘅數字",
                "example": "I have five fingers!",
                "example_cantonese": "我有五隻手指！",
                "image_url": "5️⃣",
                "physical_action": "Hold up all five fingers on one hand",
                "contexts": ["number", "count", "hand", "five"],
                "related_words": []
            },
            {
                "word": "Six",
                "word_cantonese": "六",
                "category": "Numbers",
                "pronunciation": "siks",
                "jyutping": "luk6",
                "difficulty": "MEDIUM",
                "definition": "The number after five",
                "definition_cantonese": "五之後嘅數字",
                "example": "I count to six!",
                "example_cantonese": "我數到六！",
                "image_url": "6️⃣",
                "physical_action": "Hold up six fingers (one hand and one finger)",
                "contexts": ["number", "count", "math"],
                "related_words": []
            },
            {
                "word": "Seven",
                "word_cantonese": "七",
                "category": "Numbers",
                "pronunciation": "sev-uhn",
                "jyutping": "cat1",
                "difficulty": "MEDIUM",
                "definition": "The number after six",
                "definition_cantonese": "六之後嘅數字",
                "example": "There are seven days in a week!",
                "example_cantonese": "一個禮拜有七日！",
                "image_url": "7️⃣",
                "physical_action": "Hold up seven fingers",
                "contexts": ["number", "count", "week", "lucky"],
                "related_words": []
            },
            {
                "word": "Eight",
                "word_cantonese": "八",
                "category": "Numbers",
                "pronunciation": "eyt",
                "jyutping": "baat3",
                "difficulty": "MEDIUM",
                "definition": "The number after seven",
                "definition_cantonese": "七之後嘅數字",
                "example": "A spider has eight legs!",
                "example_cantonese": "蜘蛛有八隻腳！",
                "image_url": "8️⃣",
                "physical_action": "Hold up eight fingers",
                "contexts": ["number", "count", "spider"],
                "related_words": []
            },
            {
                "word": "Nine",
                "word_cantonese": "九",
                "category": "Numbers",
                "pronunciation": "nahyn",
                "jyutping": "gau2",
                "difficulty": "MEDIUM",
                "definition": "The number after eight",
                "definition_cantonese": "八之後嘅數字",
                "example": "I count to nine!",
                "example_cantonese": "我數到九！",
                "image_url": "9️⃣",
                "physical_action": "Hold up nine fingers",
                "contexts": ["number", "count", "math"],
                "related_words": []
            },
            {
                "word": "Ten",
                "word_cantonese": "十",
                "category": "Numbers",
                "pronunciation": "ten",
                "jyutping": "sap6",
                "difficulty": "MEDIUM",
                "definition": "The number after nine",
                "definition_cantonese": "九之後嘅數字",
                "example": "I have ten fingers!",
                "example_cantonese": "我有十隻手指！",
                "image_url": "🔟",
                "physical_action": "Hold up all ten fingers",
                "contexts": ["number", "count", "complete", "fingers"],
                "related_words": []
            },
            
            # ========== SHAPES (6 words) ==========
            {
                "word": "Circle",
                "word_cantonese": "圓形",
                "category": "Shapes",
                "pronunciation": "sur-kuhl",
                "jyutping": "jyun4 jing4",
                "difficulty": "EASY",
                "definition": "A round shape like a ball",
                "definition_cantonese": "圓形嘅形狀，好似波咁",
                "example": "The sun is a circle!",
                "example_cantonese": "太陽係圓形嘅！",
                "image_url": "⭕",
                "physical_action": "Draw a circle in the air with finger",
                "contexts": ["shape", "round", "ball", "geometry"],
                "related_words": []
            },
            {
                "word": "Square",
                "word_cantonese": "正方形",
                "category": "Shapes",
                "pronunciation": "skwair",
                "jyutping": "zing3 fong1 jing4",
                "difficulty": "EASY",
                "definition": "A shape with four equal sides",
                "definition_cantonese": "有四條一樣長邊嘅形狀",
                "example": "The box is a square!",
                "example_cantonese": "盒係正方形嘅！",
                "image_url": "⬜",
                "physical_action": "Draw a square in the air",
                "contexts": ["shape", "four", "equal", "geometry"],
                "related_words": []
            },
            {
                "word": "Triangle",
                "word_cantonese": "三角形",
                "category": "Shapes",
                "pronunciation": "trahy-ang-guhl",
                "jyutping": "saam1 gok3 jing4",
                "difficulty": "MEDIUM",
                "definition": "A shape with three sides",
                "definition_cantonese": "有三條邊嘅形狀",
                "example": "The roof is a triangle!",
                "example_cantonese": "屋頂係三角形嘅！",
                "image_url": "🔺",
                "physical_action": "Make a triangle with fingers",
                "contexts": ["shape", "three", "pointy", "geometry"],
                "related_words": []
            },
            {
                "word": "Heart",
                "word_cantonese": "心形",
                "category": "Shapes",
                "pronunciation": "hahrt",
                "jyutping": "sam1 jing4",
                "difficulty": "EASY",
                "definition": "A shape that means love",
                "definition_cantonese": "代表愛嘅形狀",
                "example": "I love you with all my heart!",
                "example_cantonese": "我全心全意愛你！",
                "image_url": "❤️",
                "physical_action": "Make a heart shape with hands",
                "contexts": ["shape", "love", "valentine", "emotion"],
                "related_words": []
            },
            {
                "word": "Star",
                "word_cantonese": "星形",
                "category": "Shapes",
                "pronunciation": "stahr",
                "jyutping": "sing1 jing4",
                "difficulty": "MEDIUM",
                "definition": "A shape with five points",
                "definition_cantonese": "有五個尖嘅形狀",
                "example": "The star shines bright!",
                "example_cantonese": "星閃閃發光！",
                "image_url": "⭐",
                "physical_action": "Make star shape with fingers",
                "contexts": ["shape", "points", "night", "bright"],
                "related_words": []
            },
            {
                "word": "Rectangle",
                "word_cantonese": "長方形",
                "category": "Shapes",
                "pronunciation": "rek-tang-guhl",
                "jyutping": "coeng4 fong1 jing4",
                "difficulty": "HARD",
                "definition": "A shape with four sides, two long and two short",
                "definition_cantonese": "有四條邊嘅形狀，兩條長兩條短",
                "example": "The door is a rectangle!",
                "example_cantonese": "門係長方形嘅！",
                "image_url": "▭",
                "physical_action": "Draw a rectangle in the air",
                "contexts": ["shape", "four", "long", "geometry"],
                "related_words": []
            },
            
            # ========== CLOTHING (8 words) ==========
            {
                "word": "Shirt",
                "word_cantonese": "衫",
                "category": "Clothing",
                "pronunciation": "shurt",
                "jyutping": "saam1",
                "difficulty": "EASY",
                "definition": "Clothing you wear on top",
                "definition_cantonese": "你著喺上身嘅衣服",
                "example": "I wear a blue shirt!",
                "example_cantonese": "我著藍色衫！",
                "image_url": "👕",
                "physical_action": "Point to your shirt",
                "contexts": ["clothing", "wear", "top", "daily"],
                "related_words": []
            },
            {
                "word": "Pants",
                "word_cantonese": "褲",
                "category": "Clothing",
                "pronunciation": "pants",
                "jyutping": "fu3",
                "difficulty": "EASY",
                "definition": "Clothing you wear on your legs",
                "definition_cantonese": "你著喺腳上嘅衣服",
                "example": "I wear long pants!",
                "example_cantonese": "我著長褲！",
                "image_url": "👖",
                "physical_action": "Point to your pants",
                "contexts": ["clothing", "wear", "legs", "daily"],
                "related_words": []
            },
            {
                "word": "Shoes",
                "word_cantonese": "鞋",
                "category": "Clothing",
                "pronunciation": "shooz",
                "jyutping": "haai4",
                "difficulty": "EASY",
                "definition": "What you wear on your feet",
                "definition_cantonese": "你著喺腳上嘅嘢",
                "example": "I put on my shoes!",
                "example_cantonese": "我著鞋！",
                "image_url": "👟",
                "physical_action": "Point to your shoes",
                "contexts": ["clothing", "feet", "walk", "daily"],
                "related_words": []
            },
            {
                "word": "Hat",
                "word_cantonese": "帽",
                "category": "Clothing",
                "pronunciation": "hat",
                "jyutping": "mou6",
                "difficulty": "EASY",
                "definition": "What you wear on your head",
                "definition_cantonese": "你戴喺頭上嘅嘢",
                "example": "I wear a hat in the sun!",
                "example_cantonese": "我喺太陽底下戴帽！",
                "image_url": "🎩",
                "physical_action": "Pretend to put on a hat",
                "contexts": ["clothing", "head", "sun", "protection"],
                "related_words": []
            },
            {
                "word": "Socks",
                "word_cantonese": "襪",
                "category": "Clothing",
                "pronunciation": "soks",
                "jyutping": "mat6",
                "difficulty": "EASY",
                "definition": "What you wear on your feet inside shoes",
                "definition_cantonese": "你著喺腳上、鞋入面嘅嘢",
                "example": "I wear warm socks!",
                "example_cantonese": "我著暖襪！",
                "image_url": "🧦",
                "physical_action": "Point to your socks",
                "contexts": ["clothing", "feet", "warm", "shoes"],
                "related_words": []
            },
            {
                "word": "Dress",
                "word_cantonese": "裙",
                "category": "Clothing",
                "pronunciation": "dres",
                "jyutping": "kwan4",
                "difficulty": "MEDIUM",
                "definition": "A one-piece clothing for girls",
                "definition_cantonese": "女孩著嘅一件頭衣服",
                "example": "She wears a pretty dress!",
                "example_cantonese": "佢著靚裙！",
                "image_url": "👗",
                "physical_action": "Twirl around like wearing a dress",
                "contexts": ["clothing", "girls", "pretty", "special"],
                "related_words": []
            },
            {
                "word": "Jacket",
                "word_cantonese": "褸",
                "category": "Clothing",
                "pronunciation": "jak-it",
                "jyutping": "lau1",
                "difficulty": "MEDIUM",
                "definition": "A warm coat you wear outside",
                "definition_cantonese": "你著出街嘅暖外套",
                "example": "I wear a jacket when it's cold!",
                "example_cantonese": "天氣凍我就著褸！",
                "image_url": "🧥",
                "physical_action": "Pretend to zip up a jacket",
                "contexts": ["clothing", "warm", "cold", "outside"],
                "related_words": []
            },
            {
                "word": "Glasses",
                "word_cantonese": "眼鏡",
                "category": "Clothing",
                "pronunciation": "glas-iz",
                "jyutping": "ngaan5 geng2",
                "difficulty": "MEDIUM",
                "definition": "What you wear to help you see better",
                "definition_cantonese": "你戴嚟幫你睇得清楚啲嘅嘢",
                "example": "I wear glasses to see!",
                "example_cantonese": "我戴眼鏡睇嘢！",
                "image_url": "👓",
                "physical_action": "Pretend to put on glasses",
                "contexts": ["clothing", "see", "face", "help"],
                "related_words": []
            },
        ]
        
        # Create words with all data
        words_created = 0
        words_updated = 0
        word_objects = {}  # Store for later relationship linking
        
        for word_data in words_data:
            category_name = word_data.pop("category")
            category_id = categories[category_name].id
            
            # Check if word exists
            result = await db.execute(select(Word).where(Word.word == word_data["word"]))
            existing_word = result.scalars().first()
            
            if existing_word:
                # Update existing word
                for key, value in word_data.items():
                    if key != "related_words":  # Skip related_words for now
                        setattr(existing_word, key, value)
                setattr(existing_word, "category", category_id)
                word_objects[word_data["word"]] = existing_word
                words_updated += 1
                if words_updated % 10 == 0:
                    print(f"  Updated {words_updated} words...")
            else:
                # Create new word
                word = Word(
                    id=str(uuid.uuid4()),
                    category=category_id,
                    **{k: v for k, v in word_data.items() if k != "related_words"}
                )
                db.add(word)
                word_objects[word_data["word"]] = word
                words_created += 1
                if words_created % 10 == 0:
                    print(f"  Created {words_created} words...")
        
        await db.commit()
        print(f"\n✅ Created {words_created} new words, updated {words_updated} existing words\n")
        
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
        print(f"✅ All words include:")
        print(f"   - English and Cantonese translations")
        print(f"   - Pronunciation (English) and Jyutping (Cantonese)")
        print(f"   - Definitions and examples in both languages")
        print(f"   - Physical actions for kinesthetic learning")
        print(f"   - Contexts for real-world usage")
        print(f"   - Difficulty levels (EASY, MEDIUM, HARD)")
        print(f"   - Emoji icons")
        print("=" * 60)
        print("\n🚀 Your vocabulary platform is ready to use!\n")


if __name__ == "__main__":
    print("🌱 Starting comprehensive database seeding...\n")
    asyncio.run(seed_comprehensive_data())
