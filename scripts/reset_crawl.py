import psycopg2
try:
    conn = psycopg2.connect(host='localhost', port=5432, database='b2b_intelligence', user='marketai', password='marketai')
    cur = conn.cursor()
    cur.execute("DELETE FROM contacts WHERE source = 'web_crawl'")
    conn.commit()
    print(f"Deleted {cur.rowcount} contacts")
    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
