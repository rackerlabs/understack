"""Add Understack router VNI allocation table.

Revision ID: 5b7f7d0f4b2a
Revises: start_neutron_understack
Create Date: 2026-07-01 00:00:00.000000

"""

import sqlalchemy as sa
from neutron.db import migration
from neutron.db.migration import cli

revision = "5b7f7d0f4b2a"
down_revision = "start_neutron_understack"
branch_labels = (cli.EXPAND_BRANCH,)


def upgrade():
    migration.create_table_if_not_exists(
        "understack_router_vni_allocations",
        sa.Column("vni", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("router_id", sa.String(length=36), nullable=True),
        sa.Column(
            "allocated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("released_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["router_id"], ["routers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("vni"),
        sa.UniqueConstraint(
            "router_id",
            name="uniq_understack_router_vni_allocations0router_id",
        ),
    )
