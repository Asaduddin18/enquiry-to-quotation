import os

import psycopg
from psycopg.rows import dict_row


def connect():
    return psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row)


def initialize():
    with connect() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS enquiry_intake (
                id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                message_key text UNIQUE NOT NULL,
                digest text NOT NULL,
                raw_email bytea NOT NULL,
                source jsonb NOT NULL,
                status text NOT NULL DEFAULT 'received',
                candidate jsonb,
                issues jsonb NOT NULL DEFAULT '[]'
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS enquiry_extraction_attempt (
                id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                enquiry_id bigint NOT NULL REFERENCES enquiry_intake(id),
                attempted_at timestamptz NOT NULL DEFAULT now(),
                status text NOT NULL,
                issues jsonb NOT NULL
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS enquiry_review (
                enquiry_id bigint NOT NULL REFERENCES enquiry_intake(id),
                version integer NOT NULL,
                snapshot jsonb NOT NULL,
                revision_id bigint UNIQUE REFERENCES enquiry_intake(id),
                recorded_at timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY (enquiry_id, version)
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS supplier_approval (
                id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                enquiry_id bigint NOT NULL REFERENCES enquiry_intake(id),
                line_id text NOT NULL,
                requirement_key text NOT NULL,
                selection jsonb NOT NULL,
                recorded_at timestamptz NOT NULL DEFAULT now()
            )
        """)
