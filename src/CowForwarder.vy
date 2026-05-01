# pragma version ==0.4.3
# pragma nonreentrancy on

"""
@title CowForwarder
@license MIT
@author Curve Finance
@notice Forwards ERC20 or native tokens held by this contract to a fixed
        FeeReceiver set at deployment. Forwarding is permissionless
"""

from ethereum.ercs import IERC20
from snekmate.auth import ownable

initializes: ownable

exports: (
    ownable.owner,
    ownable.transfer_ownership,
    ownable.renounce_ownership,
)


event ForwardedERC20:
    token: indexed(address)
    amount: uint256

event ForwardedNative:
    amount: uint256

event SetFeeReceiver:
    previous_receiver: indexed(address)
    new_receiver: indexed(address)


fee_receiver: public(address)


@deploy
@payable
def __init__(_fee_receiver: address, _owner: address):
    """
    @notice Set the immutable fee receiver and initial owner.
    @param _fee_receiver Destination address for all forwarded funds.
    @param _owner Initial admin (can transfer ownership).
    """
    assert _fee_receiver != empty(address), "forwarder: zero receiver"
    assert _owner != empty(address), "forwarder: zero owner"

    self.fee_receiver = _fee_receiver
    log SetFeeReceiver(previous_receiver=empty(address), new_receiver=_fee_receiver)

    ownable.__init__()
    ownable._transfer_ownership(_owner)


@external
@payable
def __default__():
    pass


@external
def forward_erc20(_token: address, _amount: uint256):
    """
    @notice Send `_amount` of `_token` from this contract to the fee receiver.
    @dev Permissionless. Uses `default_return_value=True` to support tokens
         that do not return a bool from `transfer` (e.g. USDT-style).
    @param _token ERC20 token address.
    @param _amount Amount to forward.
    """
    assert extcall IERC20(_token).transfer(
        self.fee_receiver, _amount, default_return_value=True
    )
    log ForwardedERC20(token=_token, amount=_amount)


@external
def forward_native():
    """
    @notice Send the entire native balance of this contract to the fee receiver.
    @dev Permissionless. Uses `raw_call` to forward all gas-free of return-data
         constraints; reverts if the receiver rejects the transfer.
    """
    amount: uint256 = self.balance
    raw_call(self.fee_receiver, b"", value=amount)
    log ForwardedNative(amount=amount)


@external
def set_fee_receiver(_new_receiver: address):
    """
    @notice Update the destination address for forwarded funds.
    @dev Owner-only.
    @param _new_receiver New fee receiver address (non-zero).
    """
    ownable._check_owner()
    assert _new_receiver != empty(address), "forwarder: zero receiver"

    previous: address = self.fee_receiver
    self.fee_receiver = _new_receiver
    log SetFeeReceiver(previous_receiver=previous, new_receiver=_new_receiver)
