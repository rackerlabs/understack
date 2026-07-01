import sqlalchemy as sa
from neutron_lib.db import model_base
from sqlalchemy import orm


class UnderstackRouterVNIAllocation(model_base.BASEV2):
    __tablename__ = "understack_router_vni_allocations"

    vni = sa.Column(sa.Integer(), primary_key=True, autoincrement=False)
    router_id = sa.Column(
        sa.String(36),
        sa.ForeignKey("routers.id", ondelete="SET NULL"),
        nullable=True,
    )
    allocated_at = sa.Column(
        sa.DateTime(),
        nullable=False,
        server_default=sa.func.now(),
    )
    released_at = sa.Column(sa.DateTime(), nullable=True)

    __table_args__ = (
        sa.UniqueConstraint(
            "router_id",
            name="uniq_understack_router_vni_allocations0router_id",
        ),
        model_base.BASEV2.__table_args__,
    )

    router = orm.relationship(
        "Router",
        lazy="noload",
        load_on_pending=True,
        viewonly=True,
        backref=orm.backref(
            "understack_vni_allocation",
            lazy="selectin",
            uselist=False,
            viewonly=True,
        ),
    )

    revises_on_change = ("router",)
