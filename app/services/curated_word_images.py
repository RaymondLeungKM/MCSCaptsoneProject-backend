"""Curated local image assets for words that need deterministic illustrations."""

from typing import Optional


CURATED_WORD_IMAGE_URLS = {
    "Pencil": "/uploads/images/curated/pencil.svg",
    "Crayon": "/uploads/images/curated/crayon.svg",
    "Ruler": "/uploads/images/curated/ruler.svg",
    "Eraser": "/uploads/images/curated/eraser.svg",
    "Paper": "/uploads/images/curated/paper.svg",
    "Pen": "/uploads/images/curated/pen.svg",
    "Marker": "/uploads/images/curated/marker.svg",
    "Glue": "/uploads/images/curated/glue.svg",
    "Stapler": "/uploads/images/curated/stapler.svg",
    "Paper Clip": "/uploads/images/curated/paper-clip.svg",
}


def get_curated_word_image_url(word: str) -> Optional[str]:
    return CURATED_WORD_IMAGE_URLS.get(word)