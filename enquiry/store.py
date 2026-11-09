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
        db.execute("""
            CREATE TABLE IF NOT EXISTS rfq_package (
                approval_id bigint PRIMARY KEY REFERENCES supplier_approval(id),
                reference text UNIQUE NOT NULL,
                draft bytea NOT NULL,
                workbook bytea NOT NULL,
                approved_at timestamptz
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS supplier_reply (
                id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                message_key text UNIQUE NOT NULL,
                digest text NOT NULL,
                raw_email bytea NOT NULL,
                received_at timestamptz NOT NULL,
                reference text REFERENCES rfq_package(reference),
                supplier_id text,
                terms jsonb,
                issue text,
                review_action text,
                review_reason text
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS sourcing_selection (
                id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                reference text NOT NULL REFERENCES rfq_package(reference),
                reply_id bigint NOT NULL REFERENCES supplier_reply(id),
                reason text NOT NULL,
                recorded_at timestamptz NOT NULL DEFAULT now()
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS customer_quote (
                enquiry_id bigint REFERENCES enquiry_intake(id),
                revision integer NOT NULL,
                snapshot jsonb NOT NULL,
                pdf bytea NOT NULL,
                email bytea NOT NULL,
                exception_reason text,
                approved_at timestamptz,
                released_at timestamptz,
                issued_at timestamptz,
                sent_reference text,
                PRIMARY KEY (enquiry_id, revision)
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS confirmed_purchase (
                enquiry_id bigint NOT NULL,
                revision integer NOT NULL,
                line_id text NOT NULL,
                purchase_reference text NOT NULL,
                details jsonb NOT NULL,
                PRIMARY KEY (enquiry_id, revision, line_id, purchase_reference),
                FOREIGN KEY (enquiry_id, revision) REFERENCES customer_quote(enquiry_id, revision)
            )
        """)
