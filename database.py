import sqlite3
import os

DB_FILE = "database.db"
VAULT_FILE = "eris_vault.db"


def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            google_id TEXT NOT NULL,
            title TEXT DEFAULT 'New Chat',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        )
    """)
    conn.commit()
    conn.close()
    init_vault_db()


def init_vault_db():
    conn = sqlite3.connect(VAULT_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memory_vault (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            google_id TEXT NOT NULL,
            source_session_id TEXT,
            key_insight TEXT,
            content_vector_summary TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def global_rag_search(google_id, query_text):
    context_crumbs = []
    try:
        conn = sqlite3.connect(VAULT_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        keywords = [f"%{word}%" for word in query_text.split()
                    if len(word) > 3]
        if not keywords:
            keywords = [f"%{query_text}%"]

        for kw in keywords[:3]:
            cursor.execute("""
                SELECT key_insight, content_vector_summary FROM memory_vault 
                WHERE google_id = ? AND (key_insight LIKE ? OR content_vector_summary LIKE ?)
                LIMIT 2
            """, (google_id, kw, kw))
            for row in cursor.fetchall():
                context_crumbs.append(f"[Past Memory]: {row['key_insight']}")
        conn.close()

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT content FROM messages 
            WHERE role = 'user' AND session_id IN (SELECT id FROM sessions WHERE google_id = ?)
            ORDER BY timestamp DESC LIMIT 3
        """, (google_id,))
        for row in cursor.fetchall():
            if row['content'] != query_text:
                context_crumbs.append(f"[Recent Context]: {row['content']}")
        conn.close()

    except Exception as e:
        print(f"RAG search processing bypass: {str(e)}")

    return "\n".join(context_crumbs) if context_crumbs else "No direct historical matches."
