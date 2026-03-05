#!/usr/bin/env python3
import psycopg2

conn = psycopg2.connect('postgresql://vocab_user:Abcd1234@localhost/preschool_vocab_db')
cur = conn.cursor()
cur.execute("SELECT word, image_url FROM words WHERE image_url LIKE '%uploads/images/%' LIMIT 5")
rows = cur.fetchall()

print(f"Found {len(rows)} words with uploaded images:")
for word, url in rows:
    print(f"  {word}: {url}")

conn.close()
