import boa


ZERO_ADDR = "0x0000000000000000000000000000000000000000"


def test_constructor_sets_state(forwarder, owner, fee_receiver):
    assert forwarder.owner() == owner
    assert forwarder.fee_receiver() == fee_receiver


def test_constructor_rejects_zero_receiver(owner):
    with boa.reverts("forwarder: zero receiver"):
        boa.load("src/CowForwarder.vy", ZERO_ADDR, owner)


def test_constructor_rejects_zero_owner(fee_receiver):
    with boa.reverts("forwarder: zero owner"):
        boa.load("src/CowForwarder.vy", fee_receiver, ZERO_ADDR)


def test_forward_erc20_transfers_to_fee_receiver(
    forwarder, token, fee_receiver, stranger
):
    amount = 1_000 * 10**18
    token.mint(forwarder.address, amount)

    with boa.env.prank(stranger):
        forwarder.forward_erc20(token.address, amount)

    assert token.balanceOf(forwarder.address) == 0
    assert token.balanceOf(fee_receiver) == amount


def test_forward_erc20_partial_amount(forwarder, token, fee_receiver, stranger):
    minted = 1_000 * 10**18
    sent = 250 * 10**18
    token.mint(forwarder.address, minted)

    with boa.env.prank(stranger):
        forwarder.forward_erc20(token.address, sent)

    assert token.balanceOf(forwarder.address) == minted - sent
    assert token.balanceOf(fee_receiver) == sent


def test_forward_erc20_zero_amount(forwarder, token, fee_receiver, stranger):
    with boa.env.prank(stranger):
        forwarder.forward_erc20(token.address, 0)

    assert token.balanceOf(fee_receiver) == 0


def test_forward_erc20_emits_event(forwarder, token, stranger):
    amount = 5 * 10**18
    token.mint(forwarder.address, amount)

    with boa.env.prank(stranger):
        forwarder.forward_erc20(token.address, amount)

    events = forwarder.get_logs()
    matching = [e for e in events if type(e).__name__ == "ForwardedERC20"]
    assert len(matching) == 1
    assert matching[0].token == token.address
    assert matching[0].amount == amount


def test_forward_erc20_reverts_on_insufficient_balance(forwarder, token, stranger):
    token.mint(forwarder.address, 1)
    with boa.env.prank(stranger):
        with boa.reverts("insufficient balance"):
            forwarder.forward_erc20(token.address, 2)


def test_forward_erc20_supports_no_return_token(
    forwarder, no_return_token, fee_receiver, stranger
):
    amount = 42 * 10**18
    no_return_token.mint(forwarder.address, amount)

    with boa.env.prank(stranger):
        forwarder.forward_erc20(no_return_token.address, amount)

    assert no_return_token.balanceOf(fee_receiver) == amount


def test_forward_erc20_reverts_on_false_returning_token(
    forwarder, false_token, stranger
):
    with boa.env.prank(stranger):
        with boa.reverts():
            forwarder.forward_erc20(false_token.address, 1)


def test_forward_erc20_is_permissionless(forwarder, token, fee_receiver):
    amount = 7 * 10**18
    token.mint(forwarder.address, amount)
    random_eoa = boa.env.generate_address("random_eoa")

    with boa.env.prank(random_eoa):
        forwarder.forward_erc20(token.address, amount)

    assert token.balanceOf(fee_receiver) == amount


def test_forward_native_transfers_balance(forwarder, fee_receiver, stranger):
    amount = 3 * 10**18
    boa.env.set_balance(forwarder.address, amount)
    boa.env.set_balance(fee_receiver, 0)

    with boa.env.prank(stranger):
        forwarder.forward_native()

    assert boa.env.get_balance(forwarder.address) == 0
    assert boa.env.get_balance(fee_receiver) == amount


def test_forward_native_zero_balance(forwarder, fee_receiver, stranger):
    boa.env.set_balance(forwarder.address, 0)
    boa.env.set_balance(fee_receiver, 0)

    with boa.env.prank(stranger):
        forwarder.forward_native()

    assert boa.env.get_balance(fee_receiver) == 0


def test_forward_native_emits_event(forwarder, stranger):
    amount = 9 * 10**18
    boa.env.set_balance(forwarder.address, amount)

    with boa.env.prank(stranger):
        forwarder.forward_native()

    events = forwarder.get_logs()
    matching = [e for e in events if type(e).__name__ == "ForwardedNative"]
    assert len(matching) == 1
    assert matching[0].amount == amount


def test_forward_native_is_permissionless(forwarder, fee_receiver):
    amount = 1 * 10**18
    boa.env.set_balance(forwarder.address, amount)
    boa.env.set_balance(fee_receiver, 0)
    random_eoa = boa.env.generate_address("random_eoa")

    with boa.env.prank(random_eoa):
        forwarder.forward_native()

    assert boa.env.get_balance(fee_receiver) == amount


def test_forward_native_reverts_when_receiver_rejects(
    owner, rejecting_receiver, stranger
):
    forwarder = boa.load("src/CowForwarder.vy", rejecting_receiver.address, owner)
    boa.env.set_balance(forwarder.address, 10**18)

    with boa.env.prank(stranger):
        with boa.reverts():
            forwarder.forward_native()


def test_default_function_accepts_native(forwarder):
    sender = boa.env.generate_address("sender")
    boa.env.set_balance(sender, 5 * 10**18)
    boa.env.set_balance(forwarder.address, 0)

    boa.env.raw_call(
        to_address=forwarder.address,
        sender=sender,
        data=b"",
        value=2 * 10**18,
    )

    assert boa.env.get_balance(forwarder.address) == 2 * 10**18


def test_set_fee_receiver_updates_state(forwarder, owner):
    new_receiver = boa.env.generate_address("new_receiver")

    with boa.env.prank(owner):
        forwarder.set_fee_receiver(new_receiver)

    assert forwarder.fee_receiver() == new_receiver


def test_set_fee_receiver_emits_event(forwarder, owner, fee_receiver):
    new_receiver = boa.env.generate_address("new_receiver")

    with boa.env.prank(owner):
        forwarder.set_fee_receiver(new_receiver)

    events = forwarder.get_logs()
    matching = [e for e in events if type(e).__name__ == "SetFeeReceiver"]
    assert len(matching) == 1
    assert matching[0].previous_receiver == fee_receiver
    assert matching[0].new_receiver == new_receiver


def test_set_fee_receiver_only_owner(forwarder, stranger):
    new_receiver = boa.env.generate_address("new_receiver")

    with boa.env.prank(stranger):
        with boa.reverts():
            forwarder.set_fee_receiver(new_receiver)


def test_set_fee_receiver_rejects_zero(forwarder, owner):
    with boa.env.prank(owner):
        with boa.reverts("forwarder: zero receiver"):
            forwarder.set_fee_receiver(ZERO_ADDR)


def test_set_fee_receiver_redirects_subsequent_forwards(
    forwarder, token, owner, fee_receiver, stranger
):
    new_receiver = boa.env.generate_address("new_receiver")

    with boa.env.prank(owner):
        forwarder.set_fee_receiver(new_receiver)

    amount = 11 * 10**18
    token.mint(forwarder.address, amount)
    with boa.env.prank(stranger):
        forwarder.forward_erc20(token.address, amount)

    assert token.balanceOf(fee_receiver) == 0
    assert token.balanceOf(new_receiver) == amount


def test_transfer_ownership(forwarder, owner):
    new_owner = boa.env.generate_address("new_owner")

    with boa.env.prank(owner):
        forwarder.transfer_ownership(new_owner)

    assert forwarder.owner() == new_owner


def test_transfer_ownership_only_owner(forwarder, stranger):
    new_owner = boa.env.generate_address("new_owner")

    with boa.env.prank(stranger):
        with boa.reverts():
            forwarder.transfer_ownership(new_owner)


def test_transfer_ownership_grants_set_fee_receiver(
    forwarder, owner, fee_receiver
):
    new_owner = boa.env.generate_address("new_owner")
    with boa.env.prank(owner):
        forwarder.transfer_ownership(new_owner)

    new_receiver = boa.env.generate_address("new_receiver")
    with boa.env.prank(new_owner):
        forwarder.set_fee_receiver(new_receiver)
    assert forwarder.fee_receiver() == new_receiver

    with boa.env.prank(owner):
        with boa.reverts():
            forwarder.set_fee_receiver(fee_receiver)


def test_renounce_ownership(forwarder, owner):
    with boa.env.prank(owner):
        forwarder.renounce_ownership()

    assert forwarder.owner() == ZERO_ADDR


def test_renounce_ownership_locks_set_fee_receiver(forwarder, owner):
    with boa.env.prank(owner):
        forwarder.renounce_ownership()

    new_receiver = boa.env.generate_address("new_receiver")
    with boa.env.prank(owner):
        with boa.reverts():
            forwarder.set_fee_receiver(new_receiver)


def test_forward_erc20_after_renounce_still_works(
    forwarder, token, owner, fee_receiver, stranger
):
    with boa.env.prank(owner):
        forwarder.renounce_ownership()

    amount = 4 * 10**18
    token.mint(forwarder.address, amount)
    with boa.env.prank(stranger):
        forwarder.forward_erc20(token.address, amount)

    assert token.balanceOf(fee_receiver) == amount
