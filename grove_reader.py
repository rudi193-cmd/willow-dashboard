"""grove_reader.py — Direct Postgres reader for Grove and routing data.
b17: WDASH  ΔΣ=42
"""
import os
from datetime import datetime, timezone

# ── Color hash palette (ANSI 16, maps to curses color pair numbers 11-17) ────
_HASH_PAIRS = [11, 12, 13, 14, 15, 16, 17]


def color_for_sender(name: str) -> int:
    """Return a stable curses color_pair number for this sender name."""
    return _HASH_PAIRS[hash(name) % len(_HASH_PAIRS)]


def _pg_conn():
    import psycopg2
    dsn = os.environ.get("WILLOW_DB_URL", "")
    if dsn:
        return psycopg2.connect(dsn)
    return psycopg2.connect(
        dbname=os.environ.get("WILLOW_PG_DB", "willow"),
        user=os.environ.get("WILLOW_PG_USER", os.environ.get("USER", "")),
    )


def grove_agents(conn=None) -> list[dict]:
    """Return agents with last_seen from grove.messages, most recent first.
    Each entry: {sender: str, last_seen_at: datetime, age_secs: int}
    """
    close = conn is None
    if conn is None:
        conn = _pg_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT sender, MAX(created_at) AS last_seen
            FROM grove.messages
            WHERE is_deleted = 0
            GROUP BY sender
            ORDER BY last_seen DESC
            LIMIT 20
        """)
        now = datetime.now(timezone.utc)
        rows = []
        for sender, last_seen in cur.fetchall():
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            age_secs = int((now - last_seen).total_seconds())
            rows.append({"sender": sender, "last_seen_at": last_seen, "age_secs": age_secs})
        return rows
    except Exception:
        return []
    finally:
        if close:
            try:
                conn.close()
            except Exception:
                pass


def grove_channels(conn=None, last_seen_ids: dict | None = None) -> list[dict]:
    """Return channels with unread counts.
    last_seen_ids: {channel_name: last_seen_message_id}
    Each entry: {id: int, name: str, unread: int}
    """
    close = conn is None
    if conn is None:
        conn = _pg_conn()
    last_seen_ids = last_seen_ids or {}
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name FROM grove.channels "
            "WHERE is_deleted = 0 OR is_deleted IS NULL ORDER BY id"
        )
        channels = cur.fetchall()
        result = []
        for ch_id, name in channels:
            last_id = last_seen_ids.get(name, 0)
            cur.execute(
                "SELECT COUNT(*) FROM grove.messages "
                "WHERE channel_id = %s AND id > %s AND is_deleted = 0",
                (ch_id, last_id),
            )
            row = cur.fetchone()
            unread = row[0] if row else 0
            result.append({"id": ch_id, "name": name, "unread": unread})
        return result
    except Exception:
        return []
    finally:
        if close:
            try:
                conn.close()
            except Exception:
                pass


def grove_messages(channel_name: str, conn=None, limit: int = 50,
                   since_id: int = 0) -> list[dict]:
    """Return messages for a channel, oldest first.
    Each entry: {id: int, sender: str, content: str, created_at: datetime}
    """
    close = conn is None
    if conn is None:
        conn = _pg_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM grove.channels WHERE name = %s LIMIT 1",
            (channel_name,),
        )
        row = cur.fetchone()
        if not row:
            return []
        ch_id = row[0]
        cur.execute(
            """
            SELECT id, sender, content, created_at
            FROM grove.messages
            WHERE channel_id = %s AND id > %s AND is_deleted = 0
            ORDER BY id DESC LIMIT %s
            """,
            (ch_id, since_id, limit),
        )
        msgs = []
        for mid, sender, content, created_at in cur.fetchall():
            msgs.append({"id": mid, "sender": sender,
                         "content": content, "created_at": created_at})
        return list(reversed(msgs))
    except Exception:
        return []
    finally:
        if close:
            try:
                conn.close()
            except Exception:
                pass


def routing_decisions(conn=None, limit: int = 8) -> list[dict]:
    """Return recent routing decisions. Returns [] if table not yet created.
    Each entry: {ts, prompt_snippet, routed_to, rule_matched, confidence, latency_ms}
    """
    close = conn is None
    if conn is None:
        conn = _pg_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ts, prompt_snippet, routed_to, rule_matched, confidence, latency_ms
            FROM willow.routing_decisions
            ORDER BY ts DESC LIMIT %s
            """,
            (limit,),
        )
        rows = []
        for ts, snippet, routed_to, rule_matched, confidence, latency_ms in cur.fetchall():
            rows.append({
                "ts": ts,
                "prompt_snippet": snippet,
                "routed_to": routed_to,
                "rule_matched": rule_matched,
                "confidence": float(confidence) if confidence is not None else 1.0,
                "latency_ms": latency_ms,
            })
        return rows
    except Exception:
        return []
    finally:
        if close:
            try:
                conn.close()
            except Exception:
                pass
