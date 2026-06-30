import sqlite3
conn = sqlite3.connect("data/speeches.db")

print("=== Schema ===")
for row in conn.execute("SELECT sql FROM sqlite_master WHERE type='table'"):
    print(row[0])

print("\n=== Indexes ===")
for row in conn.execute("SELECT sql FROM sqlite_master WHERE type='index'"):
    print(row[0])

print("\n=== Stats ===")
print("Total rows:", conn.execute("SELECT COUNT(*) FROM speeches").fetchone()[0])
print("Empty body:", conn.execute("SELECT COUNT(*) FROM speeches WHERE body IS NULL OR body=''").fetchone()[0])
print("Rated:", conn.execute("SELECT COUNT(*) FROM speeches WHERE score IS NOT NULL").fetchone()[0])
print("Unknown speaker:", conn.execute("SELECT COUNT(*) FROM speeches WHERE speaker='Unknown'").fetchone()[0])
print("\nPer bank:")
for row in conn.execute("SELECT central_bank, COUNT(*) FROM speeches GROUP BY central_bank ORDER BY central_bank"):
    print(f"  {row[0]}: {row[1]}")

conn.close()
