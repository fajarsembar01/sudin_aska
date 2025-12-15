import datetime
import decimal
import json
import os
from typing import Dict, List, Optional, Sequence, Tuple

import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Urutan tabel memastikan dependensi foreign key terpenuhi lebih dulu.
TABLES_IN_ORDER: Sequence[str] = (
    "school_classes",
    "dashboard_users",
    "web_users",
    "telegram_users",
    "portal_kecamatan",
    "portal_kelurahan",
    "portal_schools",
    "portal_rooms",
    "portal_aspects",
    "portal_school_rooms",
    "portal_assessment_periods",
    "portal_assessments",
    "portal_assessment_room_details",
    "portal_assessment_scores",
    "portal_assessment_photos",
)


def _load_env() -> Dict[str, str]:
    load_dotenv(dotenv_path=".env")
    env = {
        "DB_NAME": os.getenv("DB_NAME"),
        "DB_USER": os.getenv("DB_USER"),
        "DB_PASS": os.getenv("DB_PASS"),
        "DB_HOST": os.getenv("DB_HOST"),
        "DB_PORT": os.getenv("DB_PORT"),
    }
    missing = [k for k, v in env.items() if not v]
    if missing:
        raise ValueError(f"Missing database env vars: {', '.join(missing)}")
    return env  # type: ignore[return-value]


def get_connection():
    env = _load_env()
    return psycopg2.connect(
        dbname=env["DB_NAME"],
        user=env["DB_USER"],
        password=env["DB_PASS"],
        host=env["DB_HOST"],
        port=env["DB_PORT"],
    )


def _render_data_type(col: Dict[str, Optional[str]]) -> str:
    data_type = (col.get("data_type") or "").lower()
    char_max = col.get("character_maximum_length")
    num_precision = col.get("numeric_precision")
    num_scale = col.get("numeric_scale")

    if data_type == "character varying":
        if char_max:
            return f"VARCHAR({int(char_max)})"
        return "VARCHAR"
    if data_type == "timestamp with time zone":
        return "TIMESTAMPTZ"
    if data_type == "timestamp without time zone":
        return "TIMESTAMP"
    if data_type == "numeric":
        if num_precision and num_scale is not None:
            return f"NUMERIC({int(num_precision)},{int(num_scale)})"
        if num_precision:
            return f"NUMERIC({int(num_precision)})"
        return "NUMERIC"
    # Fallback: gunakan tipe asli dari information_schema
    return data_type.upper()


def _render_column_definition(col: Dict[str, Optional[str]]) -> str:
    parts: List[str] = [f"\"{col['column_name']}\"", _render_data_type(col)]
    if col.get("is_nullable") == "NO":
        parts.append("NOT NULL")
    default = col.get("column_default")
    if default:
        parts.append(f"DEFAULT {default}")
    return " ".join(parts)


def _fetch_columns(cur, table: str) -> List[Dict[str, Optional[str]]]:
    cur.execute(
        """
        SELECT column_name,
               data_type,
               is_nullable,
               column_default,
               character_maximum_length,
               numeric_precision,
               numeric_scale
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table,),
    )
    return list(cur.fetchall())


def _fetch_constraints(cur, table: str) -> List[Dict[str, str]]:
    cur.execute(
        """
        SELECT conname, pg_get_constraintdef(oid) AS condef, contype
        FROM pg_constraint
        WHERE conrelid = %s::regclass
          AND contype IN ('p', 'u', 'c', 'f')
        ORDER BY CASE contype
                     WHEN 'p' THEN 0
                     WHEN 'u' THEN 1
                     WHEN 'c' THEN 2
                     WHEN 'f' THEN 3
                     ELSE 4
                 END,
                 conname
        """,
        (table,),
    )
    return list(cur.fetchall())


def build_create_table(cur, table: str) -> Tuple[str, List[str], List[str]]:
    columns = _fetch_columns(cur, table)
    column_defs = [_render_column_definition(col) for col in columns]
    fk_constraints: List[str] = []
    inline_constraints = []
    for constraint in _fetch_constraints(cur, table):
        if constraint["contype"] == "f":
            fk_constraints.append(
                f'ALTER TABLE "{table}" ADD CONSTRAINT "{constraint["conname"]}" {constraint["condef"]};'
            )
        else:
            inline_constraints.append(
                f'CONSTRAINT "{constraint["conname"]}" {constraint["condef"]}'
            )

    lines = column_defs + inline_constraints
    statement = f'CREATE TABLE IF NOT EXISTS "{table}" (\n    '
    statement += ",\n    ".join(lines)
    statement += "\n);\n"
    return statement, [col["column_name"] for col in columns], fk_constraints  # type: ignore[list-item]


def _format_value(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float, decimal.Decimal)):
        return str(value)
    if isinstance(value, datetime.datetime):
        fmt = "%Y-%m-%d %H:%M:%S.%f%z" if value.tzinfo else "%Y-%m-%d %H:%M:%S.%f"
        return f"'{value.strftime(fmt)}'"
    if isinstance(value, datetime.date):
        return f"'{value.strftime('%Y-%m-%d')}'"
    if isinstance(value, (dict, list)):
        serialized = json.dumps(value, ensure_ascii=False)
        escaped = serialized.replace("'", "''")
        return f"'{escaped}'"
    text = str(value).replace("'", "''")
    return f"'{text}'"


def _fetch_rows(cur, table: str, columns: List[str]) -> List[Dict[str, object]]:
    order_clause = sql.SQL(" ORDER BY {}").format(sql.Identifier("id")) if "id" in columns else sql.SQL("")
    query = sql.SQL("SELECT {} FROM {}").format(
        sql.SQL(", ").join(sql.Identifier(c) for c in columns),
        sql.Identifier(table),
    ) + order_clause
    cur.execute(query)
    return list(cur.fetchall())


def _sequence_setval_statements(cur, table: str) -> List[str]:
    cur.execute(
        """
        SELECT column_name, pg_get_serial_sequence(%s, column_name) AS seq_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (table, table),
    )
    stmts = []
    for row in cur.fetchall():
        seq = row["seq_name"]
        col = row["column_name"]
        if not seq:
            continue
        stmts.append(
            f"SELECT setval('{seq}', COALESCE((SELECT MAX(\"{col}\") FROM \"{table}\"), 1), TRUE);"
        )
    return stmts


def export_portal(output_file: str = "portal_export.sql") -> None:
    conn = get_connection()
    fk_statements: List[str] = []
    with conn.cursor(cursor_factory=RealDictCursor) as cur, open(
        output_file, "w", encoding="utf-8"
    ) as f:
        f.write("-- Portal export with schema + data\n")
        f.write(f"-- Generated at {datetime.datetime.now().isoformat()}\n\n")
        f.write("SET search_path TO public;\n\n")

        for table in TABLES_IN_ORDER:
            cur.execute("SELECT to_regclass(%s) IS NOT NULL AS exists", (table,))
            if not cur.fetchone()["exists"]:
                continue

            f.write(f"-- Schema for table: {table}\n")
            create_stmt, columns, table_fks = build_create_table(cur, table)
            fk_statements.extend(table_fks)
            f.write(create_stmt + "\n")

            f.write(f"-- Data for table: {table}\n")
            rows = _fetch_rows(cur, table, columns)
            col_list = ", ".join(f"\"{c}\"" for c in columns)
            for row in rows:
                values = [_format_value(row[col]) for col in columns]
                val_list = ", ".join(values)
                f.write(
                    f'INSERT INTO "{table}" ({col_list}) VALUES ({val_list}) ON CONFLICT DO NOTHING;\n'
                )

            for stmt in _sequence_setval_statements(cur, table):
                f.write(stmt + "\n")

            f.write("\n")

        if fk_statements:
            f.write("-- Foreign key constraints\n")
            for stmt in fk_statements:
                f.write(stmt + "\n")

    conn.close()
    print(f"Export completed -> {output_file}")


if __name__ == "__main__":
    export_portal()
