from typing import Optional, TypedDict


class CuratedCantoneseWord(TypedDict):
    word_cantonese: str
    jyutping: str


CURATED_CANTONESE_WORDS: dict[str, CuratedCantoneseWord] = {
    "Air Conditioner": {"word_cantonese": "冷氣", "jyutping": "laang5 hei3"},
    "Apple": {"word_cantonese": "蘋果", "jyutping": "ping4 gwo2"},
    "Bag": {"word_cantonese": "袋", "jyutping": "doi2"},
    "Ball": {"word_cantonese": "波", "jyutping": "bo1"},
    "Balloon": {"word_cantonese": "氣球", "jyutping": "hei3 kau4"},
    "Banana": {"word_cantonese": "香蕉", "jyutping": "hoeng1 ziu1"},
    "Bathtub": {"word_cantonese": "浴缸", "jyutping": "juk6 gong1"},
    "Bicycle": {"word_cantonese": "單車", "jyutping": "daan1 ce1"},
    "Bird": {"word_cantonese": "雀仔", "jyutping": "zoek3 zai2"},
    "Blanket": {"word_cantonese": "被", "jyutping": "pei5"},
    "Blocks": {"word_cantonese": "積木", "jyutping": "zik1 muk6"},
    "Book": {"word_cantonese": "書", "jyutping": "syu1"},
    "Bowl": {"word_cantonese": "碗", "jyutping": "wun2"},
    "Bread": {"word_cantonese": "麵包", "jyutping": "min6 baau1"},
    "Broom": {"word_cantonese": "掃把", "jyutping": "sou3 baa2"},
    "Bus": {"word_cantonese": "巴士", "jyutping": "baa1 si6"},
    "Cake": {"word_cantonese": "蛋糕", "jyutping": "daan6 gou1"},
    "Candy": {"word_cantonese": "糖", "jyutping": "tong4"},
    "Car": {"word_cantonese": "車", "jyutping": "ce1"},
    "Carrot": {"word_cantonese": "紅蘿蔔", "jyutping": "hung4 lo4 baak6"},
    "Cat": {"word_cantonese": "貓", "jyutping": "maau1"},
    "Chair": {"word_cantonese": "椅", "jyutping": "ji2"},
    "Chocolate": {"word_cantonese": "朱古力", "jyutping": "zyu1 gu1 lik1"},
    "Clock": {"word_cantonese": "時鐘", "jyutping": "si4 zung1"},
    "Cookie": {"word_cantonese": "曲奇", "jyutping": "kuk1 kei4"},
    "Corn": {"word_cantonese": "粟米", "jyutping": "suk1 mai5"},
    "Cow": {"word_cantonese": "牛", "jyutping": "ngau4"},
    "Crayon": {"word_cantonese": "蠟筆", "jyutping": "laap6 bat1"},
    "Cup": {"word_cantonese": "杯", "jyutping": "bui1"},
    "Dog": {"word_cantonese": "狗", "jyutping": "gau2"},
    "Doll": {"word_cantonese": "公仔", "jyutping": "gung1 zai2"},
    "Dress": {"word_cantonese": "裙", "jyutping": "kwan4"},
    "Egg": {"word_cantonese": "雞蛋", "jyutping": "gai1 daan2"},
    "Eraser": {"word_cantonese": "擦膠", "jyutping": "caat3 gaau1"},
    "Fish": {"word_cantonese": "魚", "jyutping": "jyu4"},
    "Flower": {"word_cantonese": "花", "jyutping": "faa1"},
    "Fridge": {"word_cantonese": "雪櫃", "jyutping": "syut3 gwai6"},
    "Grapes": {"word_cantonese": "提子", "jyutping": "tai4 zi2"},
    "Hat": {"word_cantonese": "帽", "jyutping": "mou6"},
    "Horse": {"word_cantonese": "馬", "jyutping": "maa5"},
    "House Slippers": {"word_cantonese": "拖鞋", "jyutping": "to1 haai4"},
    "Ice Cream": {"word_cantonese": "雪糕", "jyutping": "syut3 gou1"},
    "Jacket": {"word_cantonese": "外套", "jyutping": "ngoi6 tou3"},
    "Kite": {"word_cantonese": "風箏", "jyutping": "fung1 zang1"},
    "Lamp": {"word_cantonese": "燈", "jyutping": "dang1"},
    "Lychee": {"word_cantonese": "荔枝", "jyutping": "lai6 zi1"},
    "Mango": {"word_cantonese": "芒果", "jyutping": "mong1 gwo2"},
    "Marker": {"word_cantonese": "顏色筆", "jyutping": "ngaan4 sik1 bat1"},
    "Microwave": {"word_cantonese": "微波爐", "jyutping": "mei4 bo1 lou4"},
    "Milk": {"word_cantonese": "牛奶", "jyutping": "ngau4 naai5"},
    "Mirror": {"word_cantonese": "鏡", "jyutping": "geng3"},
    "Mushroom": {"word_cantonese": "蘑菇", "jyutping": "mo4 gu1"},
    "Noodles": {"word_cantonese": "麵", "jyutping": "min6"},
    "Orange": {"word_cantonese": "橙", "jyutping": "caang2"},
    "Panda": {"word_cantonese": "熊貓", "jyutping": "hung4 maau1"},
    "Pants": {"word_cantonese": "褲", "jyutping": "fu3"},
    "Paper": {"word_cantonese": "紙", "jyutping": "zi2"},
    "Pen": {"word_cantonese": "筆", "jyutping": "bat1"},
    "Pencil": {"word_cantonese": "鉛筆", "jyutping": "jyun4 bat1"},
    "Phone": {"word_cantonese": "手機", "jyutping": "sau2 gei1"},
    "Pig": {"word_cantonese": "豬", "jyutping": "zyu1"},
    "Pillow": {"word_cantonese": "枕頭", "jyutping": "zam2 tau4"},
    "Pizza": {"word_cantonese": "薄餅", "jyutping": "bok6 beng2"},
    "Plate": {"word_cantonese": "碟", "jyutping": "dip6"},
    "Pot": {"word_cantonese": "煲", "jyutping": "bou1"},
    "Potato": {"word_cantonese": "薯仔", "jyutping": "syu4 zai2"},
    "Puzzle": {"word_cantonese": "拼圖", "jyutping": "ping3 tou4"},
    "Rabbit": {"word_cantonese": "兔仔", "jyutping": "tou3 zai2"},
    "Rice": {"word_cantonese": "飯", "jyutping": "faan6"},
    "Ruler": {"word_cantonese": "尺", "jyutping": "cek3"},
    "Scooter": {"word_cantonese": "滑板車", "jyutping": "waat6 baan2 ce1"},
    "Shampoo": {"word_cantonese": "洗頭水", "jyutping": "sai2 tau4 seoi2"},
    "Sheep": {"word_cantonese": "羊", "jyutping": "joeng4"},
    "Shirt": {"word_cantonese": "衫", "jyutping": "saam1"},
    "Shoes": {"word_cantonese": "鞋", "jyutping": "haai4"},
    "Shower": {"word_cantonese": "花灑", "jyutping": "faa1 saa2"},
    "Soap": {"word_cantonese": "番梘", "jyutping": "faan1 gaan2"},
    "Socks": {"word_cantonese": "襪", "jyutping": "maat6"},
    "Spoon": {"word_cantonese": "匙羹", "jyutping": "ci4 gang1"},
    "Strawberry": {"word_cantonese": "士多啤梨", "jyutping": "si6 do1 be1 lei2"},
    "Subway": {"word_cantonese": "地鐵", "jyutping": "dei6 tit3"},
    "Table": {"word_cantonese": "枱", "jyutping": "toi2"},
    "Taxi": {"word_cantonese": "的士", "jyutping": "dik1 si6"},
    "Teddy Bear": {"word_cantonese": "啤啤熊", "jyutping": "be1 be1 hung4"},
    "Television": {"word_cantonese": "電視", "jyutping": "din6 si6"},
    "Toilet Paper": {"word_cantonese": "廁紙", "jyutping": "ci3 zi2"},
    "Tomato": {"word_cantonese": "番茄", "jyutping": "faan4 ke2"},
    "Toothbrush": {"word_cantonese": "牙刷", "jyutping": "ngaa4 caat3"},
    "Towel": {"word_cantonese": "毛巾", "jyutping": "mou4 gan1"},
    "Train": {"word_cantonese": "火車", "jyutping": "fo2 ce1"},
    "Tree": {"word_cantonese": "樹", "jyutping": "syu6"},
    "Umbrella": {"word_cantonese": "遮", "jyutping": "ze1"},
    "Watch": {"word_cantonese": "手錶", "jyutping": "sau2 biu1"},
    "Watermelon": {"word_cantonese": "西瓜", "jyutping": "sai1 gwaa1"},
}


CATEGORY_DEFINITION_ENGLISH = {
    "Animals": "A common animal children may see in daily life.",
    "Bathroom": "A common bathroom item children use every day.",
    "Clothing": "A piece of clothing children wear every day.",
    "Electronics": "A common electronic item children may see at home.",
    "Food": "A common food children may eat every day.",
    "Fruits & Vegetables": "A common fruit or vegetable children may eat every day.",
    "Household": "A common item children may use at home.",
    "Kitchen": "A common kitchen item children may see at home.",
    "Nature": "Something children may see in nature.",
    "Stationery": "A common school item children use for learning.",
    "Toys": "A toy children like to play with.",
    "Transportation": "A common vehicle children may see outdoors.",
}


CATEGORY_DEFINITION_CANTONESE = {
    "Animals": "一種小朋友日常會見到嘅動物。",
    "Bathroom": "一種浴室入面常見嘅用品。",
    "Clothing": "一種小朋友日常會著嘅衫。",
    "Electronics": "一種屋企常見嘅電子用品。",
    "Food": "一種小朋友日常會食到嘅食物。",
    "Fruits & Vegetables": "一種小朋友日常會食到嘅蔬果。",
    "Household": "一種屋企常用嘅生活用品。",
    "Kitchen": "一種廚房入面常見嘅用品。",
    "Nature": "一種喺大自然入面會見到嘅事物。",
    "Stationery": "一種小朋友學習時會用到嘅文具。",
    "Toys": "一種小朋友鍾意玩嘅玩具。",
    "Transportation": "一種日常常見嘅交通工具。",
}


def _extract_category_name(source: Optional[str]) -> Optional[str]:
    if not source:
        return None
    if source.startswith("seed_"):
        return source[5:]
    if source in CATEGORY_DEFINITION_CANTONESE:
        return source
    return None


def get_curated_cantonese_content(word: str, source: Optional[str] = None) -> Optional[dict[str, str]]:
    entry = CURATED_CANTONESE_WORDS.get(word)
    if not entry:
        return None

    category_name = _extract_category_name(source)

    return {
        "word_english": word,
        "word_cantonese": entry["word_cantonese"],
        "jyutping": entry["jyutping"],
        "definition_english": CATEGORY_DEFINITION_ENGLISH.get(
            category_name,
            "A common daily word children may learn at home.",
        ),
        "definition_cantonese": CATEGORY_DEFINITION_CANTONESE.get(
            category_name,
            "一個小朋友日常會學到嘅詞語。",
        ),
        "example_english": f"I can see {word.lower()}.",
        "example_cantonese": f"我見到{entry['word_cantonese']}。",
        "difficulty": "easy",
    }