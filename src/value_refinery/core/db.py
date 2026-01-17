from __future__ import annotations

import duckdb


def connect(db_path: str) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(db_path)
    ensure_schema(con)
    return con


def ensure_schema(con: duckdb.DuckDBPyConnection) -> None:
    # Audit tables
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            pack_id TEXT,
            created_at BIGINT,
            input_path TEXT,
            out_dir TEXT,
            db_path TEXT,
            manifest_path TEXT,
            pack_json TEXT
        );
        """
    )

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS decisions (
            decision_id TEXT PRIMARY KEY,
            run_id TEXT,
            kind TEXT,
            target_id TEXT,
            score INTEGER,
            reasons TEXT,
            created_at BIGINT
        );
        """
    )

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS dedup (
            dedup_id TEXT PRIMARY KEY,
            run_id TEXT,
            chunk_hash TEXT,
            canonical_chunk_id TEXT,
            dup_chunk_id TEXT,
            created_at BIGINT
        );
        """
    )

    # Core data tables (now run-scoped)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS docs (
            doc_id TEXT PRIMARY KEY,
            run_id TEXT,
            source_path TEXT,
            ext TEXT,
            ingested_at BIGINT,
            bytes BIGINT,
            doc_hash TEXT
        );
        """
    )

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id TEXT PRIMARY KEY,
            run_id TEXT,
            doc_id TEXT,
            section_path TEXT,
            level INTEGER,
            chunk_hash TEXT,
            n_chars INTEGER,
            score INTEGER,
            reasons TEXT,
            text TEXT
        );
        """
    )

    # Backwards-compat (if tables existed without run_id)
    try:
        con.execute("ALTER TABLE docs ADD COLUMN run_id TEXT;")
    except Exception:
        pass
    try:
        con.execute("ALTER TABLE chunks ADD COLUMN run_id TEXT;")
    except Exception:
        pass

    # Indexes
    try:
        con.execute("CREATE INDEX IF NOT EXISTS idx_docs_run ON docs(run_id);")
        con.execute("CREATE INDEX IF NOT EXISTS idx_chunks_run ON chunks(run_id);")
        con.execute("CREATE INDEX IF NOT EXISTS idx_chunks_hash ON chunks(run_id, chunk_hash);")
        con.execute("CREATE INDEX IF NOT EXISTS idx_chunks_score ON chunks(run_id, score);")
        con.execute("CREATE INDEX IF NOT EXISTS idx_decisions_run ON decisions(run_id);")
        con.execute("CREATE INDEX IF NOT EXISTS idx_dedup_run ON dedup(run_id);")
    except Exception:
        pass
