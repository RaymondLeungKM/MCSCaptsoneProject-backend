"""
Generated Sentences model - AI-generated example sentences for words
"""
from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, DateTime, Text, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class GeneratedSentence(Base):
    """AI-generated example sentences for vocabulary words"""
    __tablename__ = "generated_sentences"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    word_id = Column(String, ForeignKey("words.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Sentence content
    sentence = Column(Text, nullable=False)  # Cantonese sentence (Traditional Chinese)
    sentence_english = Column(Text, nullable=False)  # English translation
    jyutping = Column(Text, nullable=False)  # Cantonese romanization
    
    # Metadata
    context = Column(String)  # home, school, park, supermarket, etc.
    difficulty = Column(String, default="easy")  # easy, medium, hard
    
    # Quality metrics (for future filtering/ranking)
    quality_score = Column(Float)  # Optional quality assessment score
    
    # Usage tracking
    view_count = Column(Integer, default=0)  # How many times displayed to users
    helpful_count = Column(Integer, default=0)  # How many times marked as helpful
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    word = relationship("Word", back_populates="generated_sentences")
