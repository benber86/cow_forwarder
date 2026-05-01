# pragma version ==0.4.3

balances: public(HashMap[address, uint256])
allowances: public(HashMap[address, HashMap[address, uint256]])
total_supply: public(uint256)


@external
def mint(_to: address, _amount: uint256):
    self.balances[_to] += _amount
    self.total_supply += _amount


@external
@view
def balanceOf(_owner: address) -> uint256:
    return self.balances[_owner]


@external
def approve(_spender: address, _amount: uint256) -> bool:
    self.allowances[msg.sender][_spender] = _amount
    return True


@external
def transfer(_to: address, _amount: uint256) -> bool:
    assert self.balances[msg.sender] >= _amount, "insufficient balance"
    self.balances[msg.sender] -= _amount
    self.balances[_to] += _amount
    return True


@external
def transferFrom(_from: address, _to: address, _amount: uint256) -> bool:
    assert self.balances[_from] >= _amount, "insufficient balance"
    assert self.allowances[_from][msg.sender] >= _amount, "insufficient allowance"
    self.balances[_from] -= _amount
    self.balances[_to] += _amount
    self.allowances[_from][msg.sender] -= _amount
    return True
