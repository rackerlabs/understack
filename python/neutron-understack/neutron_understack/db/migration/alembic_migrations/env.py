from logging.config import fileConfig

import sqlalchemy as sa
from alembic import context
from neutron_lib.db import model_base
from oslo_config import cfg
from oslo_db.sqlalchemy import session
from sqlalchemy import event

VERSION_TABLE = "neutron_understack_alembic_version"
MYSQL_ENGINE = None
config = context.config
neutron_config = config.neutron_config
fileConfig(config.config_file_name)
target_metadata = model_base.BASEV2.metadata


def set_mysql_engine():
    try:
        mysql_engine = neutron_config.command.mysql_engine
    except cfg.NoSuchOptError:
        mysql_engine = None

    global MYSQL_ENGINE  # noqa: PLW0603
    MYSQL_ENGINE = mysql_engine or model_base.BASEV2.__table_args__["mysql_engine"]


def run_migrations_offline():
    set_mysql_engine()
    kwargs = {"version_table": VERSION_TABLE}
    if neutron_config.database.connection:
        kwargs["url"] = neutron_config.database.connection
    else:
        kwargs["dialect_name"] = neutron_config.database.engine
    context.configure(**kwargs)

    with context.begin_transaction():
        context.run_migrations()


@event.listens_for(sa.Table, "after_parent_attach")
def set_storage_engine(target, parent):
    if MYSQL_ENGINE:
        target.kwargs["mysql_engine"] = MYSQL_ENGINE


def run_migrations_online():
    set_mysql_engine()
    engine = session.create_engine(neutron_config.database.connection)
    connection = engine.connect()
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table=VERSION_TABLE,
    )
    try:
        with context.begin_transaction():
            context.run_migrations()
    finally:
        connection.close()
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
