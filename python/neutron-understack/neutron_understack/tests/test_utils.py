from unittest.mock import patch

import pytest
from neutron.plugins.ml2.driver_context import portbindings
from neutron_lib import constants
from sqlalchemy import Column
from sqlalchemy import String
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session
from sqlalchemy.orm import sessionmaker

from neutron_understack import utils


class TestParentPortIsBound:
    def test_truthy_conditions(self, port_object):
        """Truthy conditions.

        When vif type is "other", vnic_type is "baremetal"
        and binding profile is present.
        """
        result = utils.parent_port_is_bound(port_object)
        assert result is True

    def test_vif_type_unbound(self, port_object):
        port_object.bindings[0].vif_type = portbindings.VIF_TYPE_UNBOUND
        result = utils.parent_port_is_bound(port_object)
        assert result is False

    def test_vnic_type_normal(self, port_object):
        port_object.bindings[0].vnic_type = portbindings.VNIC_NORMAL
        result = utils.parent_port_is_bound(port_object)
        assert result is False

    def test_no_binding_profile(self, port_object):
        port_object.bindings[0].profile = {}
        result = utils.parent_port_is_bound(port_object)
        assert result is False


Base = declarative_base()


class Port(Base):
    __tablename__ = "ports"
    id = Column(String, primary_key=True)
    device_id = Column(String)
    device_owner = Column(String)


@pytest.fixture(scope="function")
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = scoped_session(sessionmaker(bind=engine))
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def sample_port(db_session):
    port = Port(id="port-1", device_id="original", device_owner="owner")
    db_session.add(port)
    db_session.commit()
    return port


@pytest.fixture
def mock_get_admin_context(db_session):
    class Context:
        session = db_session

    with patch("neutron_lib.context.get_admin_context", return_value=Context()):
        yield


class TestPortFieldManipulation:
    def test_update_port_fields_updates_fields(
        self, db_session, mock_get_admin_context, sample_port
    ):
        id = sample_port.id
        utils.update_port_fields(id, {"device_id": "new-id"})
        port = db_session.query(Port).filter_by(id=id).one()
        assert port.device_id == "new-id"
        assert port.device_owner == "owner"

    def test_clear_device_id_for_port(
        self, db_session, mock_get_admin_context, sample_port
    ):
        id = sample_port.id
        utils.clear_device_id_for_port(id)
        port = db_session.query(Port).filter_by(id=id).one()
        assert port.device_id == ""

    def test_set_device_id_and_owner_for_port(
        self, db_session, mock_get_admin_context, sample_port
    ):
        id = sample_port.id
        utils.set_device_id_and_owner_for_port(id, "dev-2", "own-2")
        port = db_session.query(Port).filter_by(id=id).one()
        assert port.device_id == "dev-2"
        assert port.device_owner == "own-2"


class PortContext:
    def __init__(self, current):
        self.current = current


class TestIsRouterInterface:
    def test_router_interface_true(self):
        context = PortContext(
            current={"device_owner": constants.DEVICE_OWNER_ROUTER_INTF}
        )
        assert utils.is_router_interface(context)

    def test_router_interface_false_different_device_owner(self):
        context = PortContext(current={"device_owner": "compute:nova"})
        assert not utils.is_router_interface(context)

    def test_router_interface_false_device_owner_missing(self):
        context = PortContext(current={})
        with pytest.raises(KeyError):
            utils.is_router_interface(context)

    def test_router_interface_false_device_owner_none(self):
        context = PortContext(current={"device_owner": None})
        assert not utils.is_router_interface(context)
