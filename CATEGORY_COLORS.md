# Category Color System

## Overview

The platform now automatically assigns colors to word categories, eliminating the need for manual color specification when creating categories.

## How It Works

### Automatic Color Assignment

When creating a new category, colors are automatically assigned using:

1. **Predefined Mappings**: Common category names (e.g., "Animals", "Food", "Nature") get specific colors that match their theme
2. **Round-Robin Assignment**: New categories without predefined mappings get colors from a curated palette in sequence

### Color Palette

The system uses Tailwind-compatible color classes:

- `bg-sunny` - Yellow/Orange (bright and energetic)
- `bg-coral` - Pink/Red (warm and friendly)
- `bg-sky` - Blue (calm and trustworthy)
- `bg-mint` - Green (fresh and natural)
- `bg-lavender` - Purple (creative and imaginative)
- `bg-rose-400` - Rose (soft and gentle)
- `bg-amber-400` - Amber (warm and inviting)
- `bg-teal-400` - Teal (balanced and peaceful)
- `bg-indigo-400` - Indigo (deep and thoughtful)
- `bg-emerald-400` - Emerald (vibrant and lively)
- `bg-pink-400` - Pink (playful and fun)
- `bg-cyan-400` - Cyan (cool and refreshing)

### Predefined Category Mappings

| Category Name      | Color  | Class           |
| ------------------ | ------ | --------------- |
| Animals            | Yellow | `bg-sunny`      |
| Food               | Coral  | `bg-coral`      |
| Colors             | Blue   | `bg-sky`        |
| Nature             | Green  | `bg-mint`       |
| Family             | Purple | `bg-lavender`   |
| Vehicles/Transport | Amber  | `bg-amber-400`  |
| Body/Body Parts    | Rose   | `bg-rose-400`   |
| Clothing           | Pink   | `bg-pink-400`   |
| Home/House         | Teal   | `bg-teal-400`   |
| Numbers/Counting   | Indigo | `bg-indigo-400` |
| Shapes             | Cyan   | `bg-cyan-400`   |
| General/Other      | Gray   | `bg-slate-400`  |

## API Changes

### Creating Categories

The `color` field in `CategoryCreate` is now **optional**:

```json
{
  "name": "Animals",
  "icon": "🦁",
  "description": "Animals and wildlife"
  // color is auto-assigned
}
```

If you want to specify a custom color, you can still do so:

```json
{
  "name": "Custom Category",
  "icon": "📚",
  "color": "bg-purple-500",
  "description": "My custom category"
}
```

### Backend Logic

The automatic color assignment logic is in `app/core/category_colors.py`:

```python
from app.core.category_colors import get_category_color

# Get color based on name and position
color = get_category_color("Animals", existing_count=5)
# Returns: "bg-sunny"
```

## Fixing Existing Categories

If you have existing categories with missing or default colors, run:

```bash
python fix_category_colors.py
```

This script will:

- Scan all categories
- Update any with missing, default (`bg-sky`), or gray (`bg-gray`) colors
- Assign appropriate colors based on name and order
- Report which categories were updated

## Frontend Display

The frontend's `CategoryGrid` component automatically uses the `color` field from the API:

```tsx
<button
  className={cn(
    "flex flex-col items-center justify-center p-4 rounded-2xl",
    category.color, // Applied automatically
    "hover:border-foreground/20"
  )}
>
```

No changes needed in frontend code - it just works!

## Benefits

1. ✅ **No Manual Color Management**: Colors assigned automatically
2. ✅ **Consistent Design**: Curated color palette ensures visual harmony
3. ✅ **Semantic Colors**: Common categories get theme-appropriate colors
4. ✅ **Backwards Compatible**: Can still manually specify colors if needed
5. ✅ **Easy Maintenance**: Single source of truth for color logic
