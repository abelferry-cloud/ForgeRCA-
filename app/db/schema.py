"""Current PostgreSQL schema; historical revisions keep independent frozen DDL."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

metadata = sa.MetaData(naming_convention={
    "pk": "pk_%(table_name)s", "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s", "ck": "ck_%(table_name)s_%(constraint_name)s",
    "ix": "ix_%(table_name)s_%(column_0_name)s",
})
JSON_VALUE = JSONB(none_as_null=True)
TIMESTAMP = sa.DateTime(timezone=True)

document = sa.Table(
    "document", metadata,
    sa.Column("document_key", sa.Text, primary_key=True),
    sa.Column("source_id", sa.Text, nullable=False),
    sa.Column("document_code", sa.Text, nullable=False),
    sa.Column("revision", sa.Text, nullable=False),
    sa.Column("sha256", sa.String(64), nullable=False),
    sa.Column("models", JSON_VALUE, nullable=False),
    sa.Column("firmware_scope", sa.Text),
    sa.Column("source_url", sa.Text, nullable=False),
    sa.Column("accessed_at", sa.Date, nullable=False),
    sa.Column("source_metadata", JSON_VALUE, nullable=False),
    sa.Column("retired_at", TIMESTAMP),
    sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
    sa.UniqueConstraint("source_id", "revision"),
    sa.CheckConstraint("source_id ~ '^[A-Za-z0-9][A-Za-z0-9._-]*$' AND "
                       "revision ~ '^[A-Za-z0-9][A-Za-z0-9._-]*$'", name="identity_parts"),
    sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256"),
    sa.CheckConstraint("document_key = source_id || '@' || revision || ':' || sha256", name="document_key"),
    sa.CheckConstraint("jsonb_typeof(models) = 'array' AND models <> '[]'::jsonb", name="models"),
    sa.CheckConstraint("jsonb_typeof(source_metadata) = 'object'", name="source_metadata"),
)

chunk = sa.Table(
    "chunk", metadata,
    sa.Column("document_key", sa.Text, sa.ForeignKey("document.document_key"), primary_key=True),
    sa.Column("evidence_id", sa.Text, primary_key=True),
    sa.Column("ingest_run_id", sa.Uuid, nullable=False),
    sa.Column("chunk_type", sa.Text, nullable=False),
    sa.Column("text", sa.Text, nullable=False),
    sa.Column("evidence_locator", JSON_VALUE, nullable=False),
    sa.Column("locations", JSON_VALUE, nullable=False),
    sa.Column("section", JSON_VALUE, nullable=False),
    sa.Column("source_refs", JSON_VALUE, nullable=False),
    sa.Column("heading_refs", JSON_VALUE, nullable=False),
    sa.Column("table_row", JSON_VALUE),
    sa.Column("fault_codes", JSON_VALUE, nullable=False),
    sa.Column("safety_labels", JSON_VALUE, nullable=False),
    sa.Column("created_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
    sa.ForeignKeyConstraint(["ingest_run_id", "document_key"], ["ingest_run.ingest_run_id", "ingest_run.document_key"]),
    sa.CheckConstraint("evidence_id ~ '^ev1:[0-9a-f]{64}$'", name="evidence_id"),
    sa.CheckConstraint("chunk_type IN ('section', 'table', 'table_rows', 'fault_rows')", name="chunk_type"),
    sa.CheckConstraint("length(btrim(text)) > 0", name="text"),
    sa.CheckConstraint("jsonb_typeof(evidence_locator) = 'object'", name="evidence_locator"),
    sa.CheckConstraint("jsonb_typeof(locations) = 'array' AND locations <> '[]'::jsonb", name="locations"),
    sa.CheckConstraint("jsonb_typeof(section) = 'array' AND jsonb_typeof(heading_refs) = 'array'", name="headings"),
    sa.CheckConstraint("jsonb_typeof(source_refs) = 'array' AND source_refs <> '[]'::jsonb", name="source_refs"),
    sa.CheckConstraint("table_row IS NULL OR jsonb_typeof(table_row) = 'object'", name="table_row"),
    sa.CheckConstraint("jsonb_typeof(fault_codes) = 'array' AND jsonb_typeof(safety_labels) = 'array'", name="labels"),
)
sa.Index("ix_chunk_evidence_id", chunk.c.evidence_id)
sa.Index("ix_chunk_ingest_run_id", chunk.c.ingest_run_id)

asset = sa.Table(
    "asset", metadata,
    sa.Column("asset_id", sa.Text, primary_key=True),
    sa.Column("model", sa.Text, nullable=False),
    sa.Column("synthetic", sa.Boolean, nullable=False),
    sa.UniqueConstraint("asset_id", "model", "synthetic"),
    sa.CheckConstraint("length(btrim(asset_id)) > 0 AND length(btrim(model)) > 0", name="identity"),
)

work_order = sa.Table(
    "work_order", metadata,
    sa.Column("work_order_id", sa.Text, primary_key=True),
    sa.Column("asset_id", sa.Text, nullable=False),
    sa.Column("model", sa.Text, nullable=False),
    sa.Column("synthetic", sa.Boolean, nullable=False),
    sa.Column("incident_group", sa.Text, nullable=False),
    sa.Column("firmware_version", sa.Text),
    sa.Column("alarm_code", sa.Text, nullable=False),
    sa.Column("opened_at", TIMESTAMP, nullable=False),
    sa.Column("closed_at", TIMESTAMP, nullable=False),
    sa.Column("available_at", TIMESTAMP, nullable=False),
    sa.Column("observations", JSON_VALUE, nullable=False),
    sa.Column("confirmed_cause", sa.Text, nullable=False),
    sa.Column("action", sa.Text, nullable=False),
    sa.Column("outcome", sa.Text, nullable=False),
    sa.Column("text", sa.Text, nullable=False),
    sa.Column("locator", JSON_VALUE, nullable=False),
    sa.ForeignKeyConstraint(["asset_id", "model", "synthetic"], ["asset.asset_id", "asset.model", "asset.synthetic"]),
    sa.UniqueConstraint("work_order_id", "asset_id", "model", "synthetic", "incident_group"),
    sa.CheckConstraint("closed_at >= opened_at AND available_at >= closed_at", name="time_order"),
    sa.CheckConstraint("jsonb_typeof(observations) = 'array' AND jsonb_typeof(locator) = 'object'", name="payloads"),
    sa.CheckConstraint("length(btrim(incident_group)) > 0 AND length(btrim(alarm_code)) > 0", name="event"),
)
sa.Index("ix_work_order_asset_id", work_order.c.asset_id, work_order.c.available_at)

alarm = sa.Table(
    "alarm", metadata,
    sa.Column("alarm_id", sa.Text, primary_key=True),
    sa.Column("asset_id", sa.Text, nullable=False),
    sa.Column("model", sa.Text, nullable=False),
    sa.Column("synthetic", sa.Boolean, nullable=False),
    sa.Column("incident_group", sa.Text, nullable=False),
    sa.Column("firmware_version", sa.Text),
    sa.Column("work_order_id", sa.Text),
    sa.Column("alarm_code", sa.Text, nullable=False),
    sa.Column("occurred_at", TIMESTAMP, nullable=False),
    sa.Column("available_at", TIMESTAMP, nullable=False),
    sa.Column("text", sa.Text, nullable=False),
    sa.Column("locator", JSON_VALUE, nullable=False),
    sa.ForeignKeyConstraint(["asset_id", "model", "synthetic"], ["asset.asset_id", "asset.model", "asset.synthetic"]),
    sa.ForeignKeyConstraint(["work_order_id", "asset_id", "model", "synthetic", "incident_group"],
                            ["work_order.work_order_id", "work_order.asset_id", "work_order.model",
                             "work_order.synthetic", "work_order.incident_group"]),
    sa.CheckConstraint("available_at >= occurred_at", name="time_order"),
    sa.CheckConstraint("jsonb_typeof(locator) = 'object'", name="locator"),
    sa.CheckConstraint("length(btrim(incident_group)) > 0 AND length(btrim(alarm_code)) > 0", name="event"),
)
sa.Index("ix_alarm_asset_id", alarm.c.asset_id, alarm.c.occurred_at)
sa.Index("ix_alarm_work_order_id", alarm.c.work_order_id)

ingest_run = sa.Table(
    "ingest_run", metadata,
    sa.Column("ingest_run_id", sa.Uuid, primary_key=True),
    sa.Column("document_key", sa.Text, sa.ForeignKey("document.document_key")),
    sa.Column("input_path", sa.Text, nullable=False),
    sa.Column("input_sha256", sa.String(64), nullable=False),
    sa.Column("parser", JSON_VALUE, nullable=False),
    sa.Column("operation", sa.Text, nullable=False, server_default="append"),
    sa.Column("run_status", sa.Text, nullable=False, server_default="running"),
    sa.Column("started_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
    sa.Column("finished_at", TIMESTAMP),
    sa.Column("error_code", sa.Text),
    sa.UniqueConstraint("ingest_run_id", "document_key"),
    sa.CheckConstraint("input_sha256 ~ '^[0-9a-f]{64}$'", name="input_sha256"),
    sa.CheckConstraint("jsonb_typeof(parser) = 'object'", name="parser"),
    sa.CheckConstraint("operation IN ('append', 'replace')", name="operation"),
    sa.CheckConstraint("run_status IN ('running', 'succeeded', 'failed')", name="run_status"),
    sa.CheckConstraint("(run_status = 'running' AND finished_at IS NULL) OR "
                       "(run_status <> 'running' AND finished_at IS NOT NULL AND finished_at >= started_at)",
                       name="time_order"),
)
sa.Index("ix_ingest_run_document_key", ingest_run.c.document_key)

diagnosis_run = sa.Table(
    "diagnosis_run", metadata,
    sa.Column("diagnosis_id", sa.Uuid, primary_key=True),
    sa.Column("asset_id", sa.Text, sa.ForeignKey("asset.asset_id")),
    sa.Column("model", sa.Text, nullable=False),
    sa.Column("firmware_version", sa.Text),
    sa.Column("as_of", TIMESTAMP, nullable=False),
    sa.Column("request", JSON_VALUE, nullable=False),
    sa.Column("response", JSON_VALUE),
    sa.Column("runtime_config", JSON_VALUE, nullable=False),
    sa.Column("run_status", sa.Text, nullable=False, server_default="running"),
    sa.Column("status", sa.Text),
    sa.Column("started_at", TIMESTAMP, nullable=False, server_default=sa.func.now()),
    sa.Column("finished_at", TIMESTAMP),
    sa.Column("error_code", sa.Text),
    sa.CheckConstraint("jsonb_typeof(request) = 'object' AND jsonb_typeof(runtime_config) = 'object'", name="inputs"),
    sa.CheckConstraint("response IS NULL OR jsonb_typeof(response) = 'object'", name="response"),
    sa.CheckConstraint("run_status IN ('running', 'succeeded', 'failed')", name="run_status"),
    sa.CheckConstraint("status IN ('supported', 'insufficient', 'out_of_scope')", name="status"),
    sa.CheckConstraint("(run_status = 'running' AND finished_at IS NULL) OR "
                       "(run_status <> 'running' AND finished_at IS NOT NULL AND finished_at >= started_at)",
                       name="time_order"),
    sa.CheckConstraint("(run_status = 'succeeded' AND status IS NOT NULL AND response IS NOT NULL) OR "
                       "(run_status <> 'succeeded' AND status IS NULL AND response IS NULL)", name="result_state"),
)
sa.Index("ix_diagnosis_run_asset_id", diagnosis_run.c.asset_id)
