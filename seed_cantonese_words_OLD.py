"""
Seed the database with Cantonese vocabulary words and categories
Traditional Chinese (繁體中文) with Jyutping romanization for Hong Kong preschoolers
"""
import asyncio
import uuid
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.user import User, Child
from app.models.vocabulary import Word, Category, WordProgress
from app.models.content import Story, Game, Mission
from app.models.analytics import LearningSession, DailyStats, Achievement
from app.models.parent_analytics import DailyLearningStats, LearningInsight, WeeklyReport, ParentalControl
from app.models.generated_sentences import GeneratedSentence
from app.models.daily_words import DailyWordTracking


async def seed_cantonese_data():
    async with AsyncSessionLocal() as db:
        print("📚 Seeding database with Cantonese vocabulary...\n")
        
        # Categories with Cantonese names
        categories_data = [
            {
                "name": "Animals",
                "name_cantonese": "動物",
                "description": "Learn about different animals",
                "description_cantonese": "認識不同嘅動物",
                "icon": "🦁",
                "color": "bg-sunny",
                "sort_order": 1
            },
            {
                "name": "Food",
                "name_cantonese": "食物",
                "description": "Learn about different foods",
                "description_cantonese": "認識不同嘅食物",
                "icon": "🍎",
                "color": "bg-coral",
                "sort_order": 2
            },
            {
                "name": "Colors",
                "name_cantonese": "顏色",
                "description": "Learn about colors",
                "description_cantonese": "認識唔同嘅顏色",
                "icon": "🎨",
                "color": "bg-sky",
                "sort_order": 3
            },
            {
                "name": "Nature",
                "name_cantonese": "大自然",
                "description": "Learn about nature",
                "description_cantonese": "認識大自然",
                "icon": "🌳",
                "color": "bg-mint",
                "sort_order": 4
            },
            {
                "name": "Family",
                "name_cantonese": "家庭",
                "description": "Learn about family members",
                "description_cantonese": "認識家人",
                "icon": "👨‍👩‍👧",
                "color": "bg-lavender",
                "sort_order": 5
            },
            {
                "name": "Transportation",
                "name_cantonese": "交通工具",
                "description": "Learn about vehicles and transportation",
                "description_cantonese": "認識交通工具",
                "icon": "🚗",
                "color": "bg-ocean",
                "sort_order": 6
            },
            {
                "name": "Body Parts",
                "name_cantonese": "身體部位",
                "description": "Learn about body parts",
                "description_cantonese": "認識身體部位",
                "icon": "👋",
                "color": "bg-peach",
                "sort_order": 7
            },
            {
                "name": "Places",
                "name_cantonese": "地方",
                "description": "Learn about different places",
                "description_cantonese": "認識唔同嘅地方",
                "icon": "🏠",
                "color": "bg-rose",
                "sort_order": 8
            },
        ]
        
        categories = {}
        for cat_data in categories_data:
            # Check if category exists
            result = await db.execute(
                select(Category).where(Category.name == cat_data["name"])
            )
            category = result.scalar_one_or_none()
            
            if category:
                # Update existing category with Cantonese fields
                category.name_cantonese = cat_data["name_cantonese"]
                category.description_cantonese = cat_data["description_cantonese"]
                category.icon = cat_data["icon"]
                category.color = cat_data["color"]
                category.sort_order = cat_data["sort_order"]
                print(f"✓ Updated category: {cat_data['name']} ({cat_data['name_cantonese']})")
            else:
                # Create new category
                category = Category(
                    id=str(uuid.uuid4()),
                    **cat_data
                )
                db.add(category)
                print(f"✓ Created category: {cat_data['name']} ({cat_data['name_cantonese']})")
            
            categories[cat_data["name"]] = category
        
        await db.commit()
        print(f"\n✓ Processed {len(categories)} categories\n")
        
        # Cantonese vocabulary words
        words_data = [
            # Animals (動物)
            {
                "word": "Cat", "word_cantonese": "貓", "jyutping": "maau1",
                "category": "Animals", "difficulty": "easy",
                "definition": "A small furry pet that says meow",
                "definition_cantonese": "一種毛茸茸嘅小寵物，會喵喵叫",
                "example": "I see a cat!",
                "example_cantonese": "我見到一隻貓！",
                "physical_action": "Move hands like cat paws and say 'meow'",
                "image": "🐱"
            },
            {
                "word": "Dog", "word_cantonese": "狗", "jyutping": "gau2",
                "category": "Animals", "difficulty": "easy",
                "definition": "A friendly pet that says woof",
                "definition_cantonese": "一種友善嘅寵物，會汪汪叫",
                "example": "The dog is running!",
                "example_cantonese": "隻狗喺度跑緊！",
                "physical_action": "Pant like a dog and wag your 'tail'",
                "image": "🐶"
            },
            {
                "word": "Elephant", "word_cantonese": "大象", "jyutping": "daai6 zoeng6",
                "category": "Animals", "difficulty": "medium",
                "definition": "A very large gray animal with a long trunk",
                "definition_cantonese": "一種好大隻、灰色、有長鼻嘅動物",
                "example": "The elephant is very big!",
                "example_cantonese": "大象好大隻！",
                "physical_action": "Use your arm as a trunk and stomp like an elephant",
                "image": "🐘"
            },
            {
                "word": "Lion", "word_cantonese": "獅子", "jyutping": "si1 zi2",
                "category": "Animals", "difficulty": "medium",
                "definition": "A big cat with a mane that roars",
                "definition_cantonese": "一種有鬃毛、會吼叫嘅大貓",
                "example": "The lion roars loudly!",
                "example_cantonese": "獅子大聲咁吼！",
                "physical_action": "Roar loudly like a lion",
                "image": "🦁"
            },
            {
                "word": "Butterfly", "word_cantonese": "蝴蝶", "jyutping": "wu4 dip6",
                "category": "Animals", "difficulty": "hard",
                "definition": "A colorful insect with beautiful wings",
                "definition_cantonese": "一種有靚靚翼嘅彩色昆蟲",
                "example": "The butterfly flies in the garden!",
                "example_cantonese": "蝴蝶喺花園飛緊！",
                "physical_action": "Spread arms like wings and flutter around",
                "image": "🦋"
            },
            {
                "word": "Fish", "word_cantonese": "魚", "jyutping": "jyu4",
                "category": "Animals", "difficulty": "easy",
                "definition": "An animal that lives in water",
                "definition_cantonese": "一種住喺水入面嘅動物",
                "example": "The fish swims in the water!",
                "example_cantonese": "魚喺水入面游緊！",
                "physical_action": "Move your hands like swimming fish",
                "image": "🐟"
            },
            {
                "word": "Bird", "word_cantonese": "雀仔", "jyutping": "zoek3 zai2",
                "category": "Animals", "difficulty": "easy",
                "definition": "An animal with wings that can fly",
                "definition_cantonese": "一種有翼、識飛嘅動物",
                "example": "The bird is singing!",
                "example_cantonese": "雀仔喺度唱歌！",
                "physical_action": "Flap arms like wings and chirp",
                "image": "🐦"
            },
            
            # Food (食物)
            {
                "word": "Apple", "word_cantonese": "蘋果", "jyutping": "ping4 gwo2",
                "category": "Food", "difficulty": "easy",
                "definition": "A round red or green fruit",
                "definition_cantonese": "一種圓形、紅色或者綠色嘅生果",
                "example": "I eat an apple!",
                "example_cantonese": "我食蘋果！",
                "physical_action": "Pretend to take a big bite of an apple",
                "image": "🍎"
            },
            {
                "word": "Banana", "word_cantonese": "香蕉", "jyutping": "hoeng1 ziu1",
                "category": "Food", "difficulty": "easy",
                "definition": "A long yellow fruit",
                "definition_cantonese": "一種長形、黃色嘅生果",
                "example": "The banana is yellow!",
                "example_cantonese": "香蕉係黃色嘅！",
                "physical_action": "Peel an imaginary banana",
                "image": "🍌"
            },
            {
                "word": "Rice", "word_cantonese": "飯", "jyutping": "faan6",
                "category": "Food", "difficulty": "easy",
                "definition": "A common food we eat every day",
                "definition_cantonese": "我哋日日都食嘅食物",
                "example": "I eat rice for dinner!",
                "example_cantonese": "我晚餐食飯！",
                "physical_action": "Pretend to scoop rice with chopsticks",
                "image": "🍚"
            },
            {
                "word": "Noodles", "word_cantonese": "麵", "jyutping": "min6",
                "category": "Food", "difficulty": "easy",
                "definition": "Long thin food made from flour",
                "definition_cantonese": "用麵粉整嘅長條食物",
                "example": "I love eating noodles!",
                "example_cantonese": "我鍾意食麵！",
                "physical_action": "Slurp imaginary noodles",
                "image": "🍜"
            },
            {
                "word": "Egg", "word_cantonese": "雞蛋", "jyutping": "gai1 daan6",
                "category": "Food", "difficulty": "easy",
                "definition": "A round food from chickens",
                "definition_cantonese": "雞生嘅圓形食物",
                "example": "I eat egg for breakfast!",
                "example_cantonese": "我早餐食雞蛋！",
                "physical_action": "Crack an imaginary egg",
                "image": "🥚"
            },
            {
                "word": "Milk", "word_cantonese": "奶", "jyutping": "naai5",
                "category": "Food", "difficulty": "easy",
                "definition": "A white drink from cows",
                "definition_cantonese": "牛出嘅白色飲品",
                "example": "I drink milk every morning!",
                "example_cantonese": "我朝朝都飲奶！",
                "physical_action": "Pretend to drink from a cup",
                "image": "🥛"
            },
            
            # Colors (顏色)
            {
                "word": "Red", "word_cantonese": "紅色", "jyutping": "hung4 sik1",
                "category": "Colors", "difficulty": "easy",
                "definition": "The color of an apple or fire truck",
                "definition_cantonese": "蘋果同消防車嘅顏色",
                "example": "The apple is red!",
                "example_cantonese": "蘋果係紅色嘅！",
                "physical_action": "Point to something red",
                "image": "🔴"
            },
            {
                "word": "Blue", "word_cantonese": "藍色", "jyutping": "laam4 sik1",
                "category": "Colors", "difficulty": "easy",
                "definition": "The color of the sky and ocean",
                "definition_cantonese": "天空同海洋嘅顏色",
                "example": "The sky is blue!",
                "example_cantonese": "天空係藍色嘅！",
                "physical_action": "Point to the sky",
                "image": "🔵"
            },
            {
                "word": "Yellow", "word_cantonese": "黃色", "jyutping": "wong4 sik1",
                "category": "Colors", "difficulty": "easy",
                "definition": "The color of the sun and bananas",
                "definition_cantonese": "太陽同香蕉嘅顏色",
                "example": "The banana is yellow!",
                "example_cantonese": "香蕉係黃色嘅！",
                "physical_action": "Make a circle like the sun",
                "image": "🟡"
            },
            {
                "word": "Green", "word_cantonese": "綠色", "jyutping": "luk6 sik1",
                "category": "Colors", "difficulty": "easy",
                "definition": "The color of grass and leaves",
                "definition_cantonese": "草同樹葉嘅顏色",
                "example": "The grass is green!",
                "example_cantonese": "草係綠色嘅！",
                "physical_action": "Touch grass or a plant",
                "image": "🟢"
            },
            
            # Nature (大自然)
            {
                "word": "Tree", "word_cantonese": "樹", "jyutping": "syu6",
                "category": "Nature", "difficulty": "easy",
                "definition": "A tall plant with branches and leaves",
                "definition_cantonese": "一種高大、有樹枝同樹葉嘅植物",
                "example": "The tree is tall!",
                "example_cantonese": "樹好高！",
                "physical_action": "Stand tall with arms up like tree branches",
                "image": "🌳"
            },
            {
                "word": "Flower", "word_cantonese": "花", "jyutping": "faa1",
                "category": "Nature", "difficulty": "easy",
                "definition": "A pretty plant that smells nice",
                "definition_cantonese": "一種靚靚、香香嘅植物",
                "example": "The flower is beautiful!",
                "example_cantonese": "朵花好靚！",
                "physical_action": "Pretend to smell a flower",
                "image": "🌸"
            },
            {
                "word": "Sun", "word_cantonese": "太陽", "jyutping": "taai3 joeng4",
                "category": "Nature", "difficulty": "easy",
                "definition": "The bright light in the sky during the day",
                "definition_cantonese": "日頭天空入面嘅光",
                "example": "The sun is shining!",
                "example_cantonese": "太陽好光！",
                "physical_action": "Make a big circle with arms above head",
                "image": "☀️"
            },
            {
                "word": "Rain", "word_cantonese": "雨", "jyutping": "jyu5",
                "category": "Nature", "difficulty": "easy",
                "definition": "Water that falls from the sky",
                "definition_cantonese": "天空落嚟嘅水",
                "example": "It's raining outside!",
                "example_cantonese": "出面落緊雨！",
                "physical_action": "Wiggle fingers downward like rain",
                "image": "🌧️"
            },
            
            # Family (家庭)
            {
                "word": "Mom", "word_cantonese": "媽媽", "jyutping": "maa1 maa1",
                "category": "Family", "difficulty": "easy",
                "definition": "Your mother",
                "definition_cantonese": "你嘅母親",
                "example": "I love my mom!",
                "example_cantonese": "我好愛媽媽！",
                "physical_action": "Give a big hug",
                "image": "👩"
            },
            {
                "word": "Dad", "word_cantonese": "爸爸", "jyutping": "baa1 baa1",
                "category": "Family", "difficulty": "easy",
                "definition": "Your father",
                "definition_cantonese": "你嘅父親",
                "example": "Dad plays with me!",
                "example_cantonese": "爸爸同我玩！",
                "physical_action": "Give a big hug",
                "image": "👨"
            },
            {
                "word": "Grandma", "word_cantonese": "嫲嫲", "jyutping": "maa4 maa4",
                "category": "Family", "difficulty": "medium",
                "definition": "Your father's mother",
                "definition_cantonese": "爸爸嘅媽媽",
                "example": "Grandma tells me stories!",
                "example_cantonese": "嫲嫲講故事俾我聽！",
                "physical_action": "Pretend to rock in a rocking chair",
                "image": "👵"
            },
            {
                "word": "Grandpa", "word_cantonese": "爺爺", "jyutping": "je4 je4",
                "category": "Family", "difficulty": "medium",
                "definition": "Your father's father",
                "definition_cantonese": "爸爸嘅爸爸",
                "example": "Grandpa is kind!",
                "example_cantonese": "爺爺好好人！",
                "physical_action": "Pretend to have a long beard",
                "image": "👴"
            },
            
            # Transportation (交通工具)
            {
                "word": "Bus", "word_cantonese": "巴士", "jyutping": "baa1 si6",
                "category": "Transportation", "difficulty": "easy",
                "definition": "A big vehicle that carries many people",
                "definition_cantonese": "一種載好多人嘅大車",
                "example": "I take the bus to school!",
                "example_cantonese": "我搭巴士返學！",
                "physical_action": "Hold an imaginary steering wheel",
                "image": "🚌"
            },
            {
                "word": "Car", "word_cantonese": "車", "jyutping": "ce1",
                "category": "Transportation", "difficulty": "easy",
                "definition": "A vehicle with four wheels",
                "definition_cantonese": "一種有四個轆嘅車",
                "example": "The car is fast!",
                "example_cantonese": "架車好快！",
                "physical_action": "Pretend to drive a car",
                "image": "🚗"
            },
            {
                "word": "Airplane", "word_cantonese": "飛機", "jyutping": "fei1 gei1",
                "category": "Transportation", "difficulty": "medium",
                "definition": "A vehicle that flies in the sky",
                "definition_cantonese": "一種喺天空飛嘅交通工具",
                "example": "The airplane flies high!",
                "example_cantonese": "飛機飛好高！",
                "physical_action": "Spread arms like wings and make airplane sounds",
                "image": "✈️"
            },
            
            # Body Parts (身體部位)
            {
                "word": "Eye", "word_cantonese": "眼", "jyutping": "ngaan5",
                "category": "Body Parts", "difficulty": "easy",
                "definition": "The part of your body you use to see",
                "definition_cantonese": "你用嚟睇嘢嘅身體部位",
                "example": "I have two eyes!",
                "example_cantonese": "我有兩隻眼！",
                "physical_action": "Point to your eyes",
                "image": "👁️"
            },
            {
                "word": "Hand", "word_cantonese": "手", "jyutping": "sau2",
                "category": "Body Parts", "difficulty": "easy",
                "definition": "The part at the end of your arm",
                "definition_cantonese": "你手臂尾嘅部分",
                "example": "I wave my hand!",
                "example_cantonese": "我揮手！",
                "physical_action": "Wave your hand",
                "image": "✋"
            },
            {
                "word": "Foot", "word_cantonese": "腳", "jyutping": "goek3",
                "category": "Body Parts", "difficulty": "easy",
                "definition": "The part at the end of your leg",
                "definition_cantonese": "你腳嘅尾部",
                "example": "I walk with my feet!",
                "example_cantonese": "我用腳行路！",
                "physical_action": "Stomp your feet",
                "image": "🦶"
            },
            
            # Places (地方)
            {
                "word": "Home", "word_cantonese": "屋企", "jyutping": "uk1 kei5",
                "category": "Places", "difficulty": "easy",
                "definition": "The place where you live",
                "definition_cantonese": "你住嘅地方",
                "example": "I go home after school!",
                "example_cantonese": "我放學返屋企！",
                "physical_action": "Make a roof shape with hands above head",
                "image": "🏠"
            },
            {
                "word": "Park", "word_cantonese": "公園", "jyutping": "gung1 jyun4",
                "category": "Places", "difficulty": "easy",
                "definition": "A place with grass and playground",
                "definition_cantonese": "一個有草地同遊樂場嘅地方",
                "example": "I play at the park!",
                "example_cantonese": "我喺公園玩！",
                "physical_action": "Pretend to swing on swings",
                "image": "🏞️"
            },
            {
                "word": "School", "word_cantonese": "學校", "jyutping": "hok6 haau6",
                "category": "Places", "difficulty": "medium",
                "definition": "A place where you learn",
                "definition_cantonese": "你學嘢嘅地方",
                "example": "I learn at school!",
                "example_cantonese": "我喺學校學嘢！",
                "physical_action": "Pretend to write on a board",
                "image": "🏫"
            },
        ]
        
        word_count = 0
        for word_data in words_data:
            category = categories[word_data["category"]]
            
            # Check if word exists
            result = await db.execute(
                select(Word).where(Word.word == word_data["word"])
            )
            word = result.scalar_one_or_none()
            
            if word:
                # Update existing word with Cantonese fields
                word.word_cantonese = word_data["word_cantonese"]
                word.jyutping = word_data["jyutping"]
                word.definition_cantonese = word_data["definition_cantonese"]
                word.example_cantonese = word_data["example_cantonese"]
                word.physical_action = word_data.get("physical_action")
                print(f"✓ Updated: {word_data['word']} ({word_data['word_cantonese']}) - {word_data['jyutping']}")
            else:
                # Create new word
                word = Word(
                    id=str(uuid.uuid4()),
                    word=word_data["word"],
                    word_cantonese=word_data["word_cantonese"],
                    jyutping=word_data["jyutping"],
                    category=category.id,
                    difficulty=word_data["difficulty"],
                    definition=word_data["definition"],
                    definition_cantonese=word_data["definition_cantonese"],
                    example=word_data["example"],
                    example_cantonese=word_data["example_cantonese"],
                    pronunciation=word_data["word"].lower(),
                    physical_action=word_data.get("physical_action"),
                    is_active=True,
                    image_url=word_data.get("image"),
                    audio_url=None
                )
                db.add(word)
                print(f"✓ Created: {word_data['word']} ({word_data['word_cantonese']}) - {word_data['jyutping']}")
            
            word_count += 1
        
        await db.commit()
        print(f"\n✓ Processed {word_count} words\n")
        
        # Update word counts for each category
        for category in categories.values():
            result = await db.execute(
                select(Word).where(Word.category == category.id, Word.is_active == True)
            )
            words_in_category = result.scalars().all()
            category.word_count = len(words_in_category)
        
        await db.commit()
        print(f"✓ Updated category word counts\n")
        
        print("✅ Cantonese vocabulary seeding complete!")
        print(f"   - {len(categories)} categories (with 繁體中文)")
        print(f"   - {word_count} words (with 廣東話 & Jyutping)")
        print("\n🚀 Ready to learn Cantonese!")


if __name__ == "__main__":
    print("🌱 Starting Cantonese vocabulary seeding...\n")
    asyncio.run(seed_cantonese_data())
