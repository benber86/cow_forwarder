# pragma version ==0.4.3

balances: public(HashMap[address, uint256])


@external
def mint(_to: address, _amount: uint256):
    self.balances[_to] += _amount


@external
@view
def balanceOf(_owner: address) -> uint256:
    return self.balances[_owner]


@external
def transfer(_to: address, _amount: uint256):
    assert self.balances[msg.sender] >= _amount, "insufficient balance"
    self.balances[msg.sender] -= _amount
    self.balances[_to] += _amount
