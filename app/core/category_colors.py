"""
Automatic category color assignment
"""

# Predefined color palette for categories (Tailwind-compatible classes)
CATEGORY_COLOR_PALETTE = [
    "bg-sunny",      # Yellow/Orange - bright and energetic
    "bg-coral",      # Pink/Red - warm and friendly
    "bg-sky",        # Blue - calm and trustworthy
    "bg-mint",       # Green - fresh and natural
    "bg-lavender",   # Purple - creative and imaginative
    "bg-rose-400",   # Rose - soft and gentle
    "bg-amber-400",  # Amber - warm and inviting
    "bg-teal-400",   # Teal - balanced and peaceful
    "bg-indigo-400", # Indigo - deep and thoughtful
    "bg-emerald-400",# Emerald - vibrant and lively
    "bg-pink-400",   # Pink - playful and fun
    "bg-cyan-400",   # Cyan - cool and refreshing
]

# Predefined mappings for common category names
CATEGORY_COLOR_MAP = {
    "animals": "bg-sunny",
    "animal": "bg-sunny",
    "food": "bg-coral",
    "foods": "bg-coral",
    "colors": "bg-sky",
    "colour": "bg-sky",
    "nature": "bg-mint",
    "plants": "bg-mint",
    "family": "bg-lavender",
    "people": "bg-lavender",
    "vehicles": "bg-amber-400",
    "transport": "bg-amber-400",
    "body": "bg-rose-400",
    "body parts": "bg-rose-400",
    "clothing": "bg-pink-400",
    "clothes": "bg-pink-400",
    "home": "bg-teal-400",
    "house": "bg-teal-400",
    "numbers": "bg-indigo-400",
    "counting": "bg-indigo-400",
    "shapes": "bg-cyan-400",
    "general": "bg-slate-400",
    "General": "bg-slate-400",
    "other": "bg-slate-400",
}


def get_category_color(category_name: str, existing_categories_count: int = 0) -> str:
    """
    Get an appropriate color for a category.
    
    First checks if the category name matches a predefined mapping.
    If not, assigns a color from the palette in a round-robin fashion.
    
    Args:
        category_name: The name of the category
        existing_categories_count: Number of existing categories (for round-robin assignment)
        
    Returns:
        A Tailwind CSS background color class (e.g., "bg-sunny")
    """
    # Normalize category name for lookup
    normalized_name = category_name.lower().strip()
    
    # Check predefined mappings first
    if normalized_name in CATEGORY_COLOR_MAP:
        return CATEGORY_COLOR_MAP[normalized_name]
    
    # Otherwise, use round-robin from palette
    color_index = existing_categories_count % len(CATEGORY_COLOR_PALETTE)
    return CATEGORY_COLOR_PALETTE[color_index]


def get_next_available_color(used_colors: list[str]) -> str:
    """
    Get the next available color that hasn't been used yet.
    If all colors are used, cycles back to the start of the palette.
    
    Args:
        used_colors: List of colors already in use
        
    Returns:
        A Tailwind CSS background color class
    """
    for color in CATEGORY_COLOR_PALETTE:
        if color not in used_colors:
            return color
    
    # If all colors are used, return first color (cycling)
    return CATEGORY_COLOR_PALETTE[0]
