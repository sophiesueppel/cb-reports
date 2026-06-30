import sqlite3
conn = sqlite3.connect("data/speeches.db")
rows = conn.execute(
    "SELECT central_bank, substr(date,1,4) as yr, COUNT(*) as n "
    "FROM speeches GROUP BY central_bank, yr ORDER BY central_bank, yr"
).fetchall()
for r in rows:
    print(r)
print()
total = conn.execute("SELECT COUNT(*) FROM speeches").fetchone()[0]
print(f"Total speeches in DB: {total}")
conn.close()
