"""
Verification Script: Check Word Integrity After Enhancement
This script checks if any words had their English word field modified incorrectly
"""
import asyncio
from sqlalchemy import select, and_, or_
from app.db.session import AsyncSessionLocal
from app.models.vocabulary import Word


async def check_word_integrity():
    """Check for any words that might have been incorrectly modified"""
    
    print("=" * 70)
    print("WORD INTEGRITY CHECK")
    print("=" * 70)
    print()
    
    async with AsyncSessionLocal() as db:
        # Get all words
        result = await db.execute(
            select(Word).where(Word.is_active == True).order_by(Word.word)
        )
        words = result.scalars().all()
        
        print(f"Total active words: {len(words)}")
        print()
        
        # Check for suspicious patterns
        suspicious = []
        missing_english = []
        missing_cantonese = []
        suspicious_capitalization = []
        
        for word in words:
            # Check 1: Missing English word
            if not word.word or not word.word.strip():
                missing_english.append(word)
            
            # Check 2: Suspicious patterns in English word
            # (contains Chinese characters, too long, etc.)
            if word.word:
                # Has Chinese characters
                if any('\u4e00' <= char <= '\u9fff' for char in word.word):
                    suspicious.append((word, "English word contains Chinese characters"))
                
                # Unusually long for a single word (>20 chars)
                if len(word.word) > 20 and ' ' not in word.word:
                    suspicious.append((word, "English word unusually long"))
                
                # All lowercase (should be capitalized)
                if word.word[0].islower() and word.word not in ["iPhone", "iPad"]:
                    suspicious_capitalization.append(word)
            
            # Check 3: Suspicious patterns in Cantonese word
            if word.word_cantonese:
                # Has English characters (except special cases)
                if any(char.isalpha() and ord(char) < 128 for char in word.word_cantonese):
                    suspicious.append((word, "Cantonese word contains English letters"))
                
                # Too long (most single Cantonese words are 1-3 characters)
                if len(word.word_cantonese) > 5:
                    suspicious.append((word, "Cantonese word unusually long"))
            else:
                missing_cantonese.append(word)
        
        # Report findings
        print("📊 RESULTS:")
        print()
        
        if missing_english:
            print(f"⚠️  {len(missing_english)} words missing English text:")
            for word in missing_english[:10]:
                print(f"  - ID: {word.id}, Cantonese: {word.word_cantonese}")
            if len(missing_english) > 10:
                print(f"  ... and {len(missing_english) - 10} more")
            print()
        else:
            print("✅ All words have English text")
            print()
        
        if missing_cantonese:
            print(f"ℹ️  {len(missing_cantonese)} words missing Cantonese text:")
            for word in missing_cantonese[:10]:
                print(f"  - {word.word} (ID: {word.id})")
            if len(missing_cantonese) > 10:
                print(f"  ... and {len(missing_cantonese) - 10} more")
            print(f"  💡 Tip: Run batch-enhance to add Cantonese content")
            print()
        else:
            print("✅ All words have Cantonese text")
            print()
        
        if suspicious:
            print(f"⚠️  {len(suspicious)} words with suspicious patterns:")
            for word, reason in suspicious[:10]:
                print(f"  - {word.word} (ID: {word.id}) - {reason}")
                if word.word_cantonese:
                    print(f"    Cantonese: {word.word_cantonese}")
            if len(suspicious) > 10:
                print(f"  ... and {len(suspicious) - 10} more")
            print()
        else:
            print("✅ No suspicious patterns found")
            print()
        
        if suspicious_capitalization:
            print(f"ℹ️  {len(suspicious_capitalization)} words with lowercase start:")
            for word in suspicious_capitalization[:10]:
                print(f"  - {word.word} (ID: {word.id})")
            if len(suspicious_capitalization) > 10:
                print(f"  ... and {len(suspicious_capitalization) - 10} more")
            print()
        else:
            print("✅ All words properly capitalized")
            print()
        
        # Show sample of correctly enhanced words
        enhanced_words = [w for w in words if w.word_cantonese and w.definition_cantonese]
        print(f"✅ {len(enhanced_words)} words have been properly enhanced with bilingual content")
        print()
        
        if enhanced_words:
            print("Sample of properly enhanced words:")
            for word in enhanced_words[:5]:
                print(f"  - {word.word} / {word.word_cantonese}")
                print(f"    Definition: {word.definition[:60] if word.definition else 'None'}...")
                print(f"    定義: {word.definition_cantonese[:40] if word.definition_cantonese else 'None'}...")
                print()
        
        # Summary
        print("=" * 70)
        if not missing_english and not suspicious:
            print("✅ ALL CHECKS PASSED - Word integrity is perfect!")
            if missing_cantonese:
                print(f"ℹ️  Note: {len(missing_cantonese)} words need Cantonese content (not an error)")
        else:
            print("⚠️  ISSUES FOUND - See details above")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(check_word_integrity())
