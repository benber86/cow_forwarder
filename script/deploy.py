"""
Deploy CowForwarder to the active network via CreateX's deployCreate3,
producing a deterministic address that is identical across every chain
we target — even though the constructor args (fee_receiver, owner) may
differ per chain.

Usage:
  uv run mox run deploy --network mainnet-fork    # dry run
  uv run mox run deploy --network mainnet         # live

"""

import json
import os

import boa
from eth_abi import encode as abi_encode
from eth_utils import keccak, to_bytes, to_checksum_address

from moccasin.boa_tools import VyperContract
from moccasin.config import get_active_network


# CreateX — same address on every chain (pre-signed deterministic deploy).
# https://github.com/pcaversaccio/createx

CREATEX_ADDRESS = "0xba5Ed099633D3B313e4D5F7bdc1305d3c28ba5Ed"

CREATEX_ABI = [
    {
        "type": "function",
        "stateMutability": "payable",
        "name": "deployCreate3",
        "inputs": [
            {"name": "salt", "type": "bytes32"},
            {"name": "initCode", "type": "bytes"},
        ],
        "outputs": [{"name": "newContract", "type": "address"}],
    },
    {
        "type": "function",
        "stateMutability": "view",
        "name": "computeCreate3Address",
        "inputs": [
            {"name": "salt", "type": "bytes32"},
            {"name": "deployer", "type": "address"},
        ],
        "outputs": [{"name": "computed", "type": "address"}],
    },
]

_FORWARDER_ENTROPY_TAG = b"COW-FORWRD3"  # 11 bytes
assert len(_FORWARDER_ENTROPY_TAG) == 11


def _raw_salt(deployer: str, entropy: bytes) -> bytes:
    assert len(entropy) == 11, "entropy must be exactly 11 bytes"
    deployer_bytes = to_bytes(hexstr=to_checksum_address(deployer))
    assert len(deployer_bytes) == 20
    cross_chain_flag = b"\x00"
    salt = deployer_bytes + cross_chain_flag + entropy
    assert len(salt) == 32
    return salt


def _guarded_salt(deployer: str, raw_salt: bytes) -> bytes:
    assert len(raw_salt) == 32
    sender_b32 = b"\x00" * 12 + to_bytes(hexstr=to_checksum_address(deployer))
    assert len(sender_b32) == 32
    return keccak(sender_b32 + raw_salt)


def _forwarder_initcode(fee_receiver: str, owner: str) -> bytes:
    deployer = boa.load_partial("src/CowForwarder.vy")
    runtime = deployer.compiler_data.bytecode
    encoded_args = abi_encode(
        ["address", "address"],
        [to_checksum_address(fee_receiver), to_checksum_address(owner)],
    )
    return bytes(runtime) + encoded_args


def _get_createx():
    return boa.loads_abi(json.dumps(CREATEX_ABI), name="CreateX").at(CREATEX_ADDRESS)


def _read_constructor_args() -> tuple[str, str]:
    fee_receiver = os.environ.get("COW_FORWARDER_FEE_RECEIVER")
    owner = os.environ.get("COW_FORWARDER_OWNER")
    missing = [
        name
        for name, val in [
            ("COW_FORWARDER_FEE_RECEIVER", fee_receiver),
            ("COW_FORWARDER_OWNER", owner),
        ]
        if not val
    ]
    if missing:
        raise RuntimeError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            f"Set them in .env before running deploy — they are baked into "
            f"the deployed contract and cannot be changed without redeploying."
        )
    return to_checksum_address(fee_receiver), to_checksum_address(owner)


def deploy() -> VyperContract:
    network = get_active_network()
    chain_id = network.chain_id
    name = network.name

    fee_receiver, owner = _read_constructor_args()

    deployer_account = network.get_default_account()
    deployer_addr = (
        str(deployer_account.address)
        if hasattr(deployer_account, "address")
        else str(deployer_account)
    )

    print(f"[deploy] network          : {name} (chain_id={chain_id})")
    print(f"[deploy] deployer         : {deployer_addr}")
    print(f"[deploy] CreateX          : {CREATEX_ADDRESS}")
    print(f"[deploy] fee_receiver     : {fee_receiver}")
    print(f"[deploy] owner            : {owner}")

    createx = _get_createx()

    raw_salt = _raw_salt(deployer_addr, _FORWARDER_ENTROPY_TAG)
    guarded_salt = _guarded_salt(deployer_addr, raw_salt)
    predicted = createx.computeCreate3Address(guarded_salt, CREATEX_ADDRESS)
    print(f"[deploy] forwarder predicted : {predicted}")

    initcode = _forwarder_initcode(fee_receiver, owner)

    existing_code = boa.env.get_code(str(predicted))
    if existing_code:
        print(
            f"[deploy] forwarder already at {predicted} "
            f"({len(existing_code)} bytes) — skipping deploy"
        )
        deployed_addr = str(predicted)
    else:
        print(f"[deploy] forwarder initcode  : {len(initcode)} bytes")
        deployed = createx.deployCreate3(raw_salt, initcode)
        assert (
            str(deployed).lower() == str(predicted).lower()
        ), f"CREATE3 address mismatch: predicted={predicted} got={deployed}"
        deployed_addr = str(deployed)
        print(f"[deploy] forwarder deployed  : {deployed_addr}")

    forwarder_dep = boa.load_partial("src/CowForwarder.vy")
    forwarder_obj = forwarder_dep.at(deployed_addr)

    assert (
        str(forwarder_obj.fee_receiver()).lower() == fee_receiver.lower()
    ), "post-deploy sanity check failed: fee_receiver mismatch"
    assert (
        str(forwarder_obj.owner()).lower() == owner.lower()
    ), "post-deploy sanity check failed: owner mismatch"
    print("[deploy] post-deploy sanity OK — fee_receiver and owner match args")

    forwarder_obj.ctor_calldata = abi_encode(
        ["address", "address"], [fee_receiver, owner]
    )

    if getattr(network, "is_fork", False):
        print("[deploy] skipping explorer verification (fork network)")
    else:
        _verify_on_explorer(network, forwarder_obj, deployed_addr)

    return forwarder_obj


def _verify_on_explorer(network, forwarder_obj, forwarder_addr):
    """
    Moccasin's verification module bugs with sidechains so this is a fix until
    upstream is fixed.
    """
    print("[deploy] verifying on explorer (this can take a minute)...")
    verifier_class = network.get_verifier_class()
    verifier = verifier_class(
        network.explorer_uri,
        network.explorer_api_key,
        chain_id=network.chain_id,
    )

    result = boa.verify(forwarder_obj, verifier)
    result.wait_for_verification()
    print(f"[deploy] forwarder verified : {forwarder_addr}")


def moccasin_main() -> VyperContract:
    return deploy()
