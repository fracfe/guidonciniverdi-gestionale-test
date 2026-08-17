"""estende job wordpress per stato operativo

Revision ID: 91c4f2b7a6de
Revises: 42b33e98a7ee
Create Date: 2026-08-17

"""
import json

from alembic import op
import sqlalchemy as sa


revision = "91c4f2b7a6de"
down_revision = "42b33e98a7ee"
branch_labels = None
depends_on = None


def _payload(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            return decoded if isinstance(decoded, dict) else {}
        except (TypeError, ValueError):
            return {}
    return {}


def upgrade():
    with op.batch_alter_table("job_wordpress", schema=None) as batch_op:
        batch_op.add_column(sa.Column("tipo", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("iscrizione_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("started_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column("attempts", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(sa.Column("last_error", sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            "fk_job_wordpress_iscrizioni_id",
            "iscrizioni_eg",
            ["iscrizione_id"],
            ["id"],
            ondelete="SET NULL",
        )

    connection = op.get_bind()
    jobs = sa.table(
        "job_wordpress",
        sa.column("id", sa.Integer()),
        sa.column("data", sa.DateTime()),
        sa.column("stato", sa.String()),
        sa.column("dati", sa.JSON()),
        sa.column("tipo", sa.String()),
        sa.column("iscrizione_id", sa.Integer()),
        sa.column("started_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    iscrizioni = sa.table(
        "iscrizioni_eg",
        sa.column("id", sa.Integer()),
    )
    iscrizioni_esistenti = set(
        connection.execute(sa.select(iscrizioni.c.id)).scalars()
    )
    for job in connection.execute(
        sa.select(jobs.c.id, jobs.c.data, jobs.c.stato, jobs.c.dati)
    ):
        dati = _payload(job.dati)
        tipo = dati.get("tipo")
        if not isinstance(tipo, str) or not tipo:
            tipo = "crea_sq"
        iscrizione_id = dati.get("iscrizione")
        if (
            type(iscrizione_id) is not int
            or iscrizione_id not in iscrizioni_esistenti
        ):
            iscrizione_id = None
        connection.execute(
            jobs.update()
            .where(jobs.c.id == job.id)
            .values(
                tipo=tipo,
                iscrizione_id=iscrizione_id,
                started_at=job.data if job.stato == "SENDING" else None,
                updated_at=job.data,
            )
        )

    with op.batch_alter_table("job_wordpress", schema=None) as batch_op:
        batch_op.alter_column("tipo", existing_type=sa.String(255), nullable=False)
        batch_op.alter_column("updated_at", existing_type=sa.DateTime(), nullable=False)
        batch_op.create_index(
            "ix_job_wordpress_iscrizione_stato",
            ["iscrizione_id", "stato"],
            unique=False,
        )
        batch_op.create_index(
            "ix_job_wordpress_stato_updated_at",
            ["stato", "updated_at"],
            unique=False,
        )
        batch_op.create_index(
            "ix_job_wordpress_iscrizione_tipo_id",
            ["iscrizione_id", "tipo", "id"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("job_wordpress", schema=None) as batch_op:
        batch_op.drop_index("ix_job_wordpress_iscrizione_tipo_id")
        batch_op.drop_index("ix_job_wordpress_stato_updated_at")
        batch_op.drop_index("ix_job_wordpress_iscrizione_stato")
        batch_op.drop_constraint(
            "fk_job_wordpress_iscrizioni_id", type_="foreignkey"
        )
        batch_op.drop_column("last_error")
        batch_op.drop_column("attempts")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("started_at")
        batch_op.drop_column("iscrizione_id")
        batch_op.drop_column("tipo")
