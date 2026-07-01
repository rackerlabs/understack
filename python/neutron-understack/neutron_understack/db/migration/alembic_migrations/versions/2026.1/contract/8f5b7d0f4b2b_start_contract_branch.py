"""Start neutron-understack contract branch.

Revision ID: 8f5b7d0f4b2b
Revises: start_neutron_understack
Create Date: 2026-07-01 00:00:00.000000

"""

from neutron.db.migration import cli

revision = "8f5b7d0f4b2b"
down_revision = "start_neutron_understack"
branch_labels = (cli.CONTRACT_BRANCH,)


def upgrade():
    pass
