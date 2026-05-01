# pragma version ==0.4.3


@external
@view
def balanceOf(_owner: address) -> uint256:
    return 0


@external
def transfer(_to: address, _amount: uint256) -> bool:
    return False
