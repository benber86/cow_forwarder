import boa
import pytest


ZERO_ADDR = "0x0000000000000000000000000000000000000000"


@pytest.fixture
def owner():
    return boa.env.generate_address("owner")


@pytest.fixture
def fee_receiver():
    return boa.env.generate_address("fee_receiver")


@pytest.fixture
def stranger():
    return boa.env.generate_address("stranger")


@pytest.fixture
def forwarder(owner, fee_receiver):
    return boa.load("src/CowForwarder.vy", fee_receiver, owner)


@pytest.fixture
def token():
    return boa.load("tests/mocks/MockERC20.vy")


@pytest.fixture
def no_return_token():
    return boa.load("tests/mocks/MockNoReturnERC20.vy")


@pytest.fixture
def false_token():
    return boa.load("tests/mocks/MockFalseERC20.vy")


@pytest.fixture
def rejecting_receiver():
    return boa.load("tests/mocks/RejectingReceiver.vy")
