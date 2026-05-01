"""
Deploy CowForwarder to the active network via CreateX's deployCreate3,
producing a deterministic address that is identical across every chain
we target — even though the constructor args (fee_receiver, owner) may
differ per chain.

Per-chain (fee_receiver, owner) live in CHAIN_CONFIG below — committed
with the code, reviewed in PRs, no env vars to mis-set at deploy time.
Adding a new chain means adding an entry there.

Usage:
  uv run mox run deploy --network mainnet-fork    # dry run
  uv run mox run deploy --network mainnet         # live

"""

import json
from dataclasses import dataclass

import boa
from eth_abi import encode as abi_encode
from eth_utils import keccak, to_bytes, to_checksum_address

from moccasin.boa_tools import VyperContract
from moccasin.config import get_active_network


@dataclass(frozen=True)
class ChainConfig:
    fee_receiver: str
    owner: str


CHAIN_CONFIG: dict[int, ChainConfig] = {
    # Ethereum
    # 1: ChainConfig(
    #     fee_receiver="0x...",
    #     owner="0x...",
    # ),
    # Arbitrum
    42161: ChainConfig(
        fee_receiver="0xd4F94D0aaa640BBb72b5EEc2D85F6D114D81a88E",
        owner="0x452030a5D962d37D97A9D65487663cD5fd9C2B32",
    ),
    # Gnosis
    100: ChainConfig(
        fee_receiver="0xBb7404F9965487a9DdE721B3A5F0F3CcfA9aa4C5",
        owner="0x0b98718264cA14d0A17C145FfE1e4F3c38a39372",
    ),
    # Sepolia
    11155111: ChainConfig(
        fee_receiver="0x0b98718264cA14d0A17C145FfE1e4F3c38a39372",
        owner="0x0b98718264cA14d0A17C145FfE1e4F3c38a39372",
    ),
}


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


def _read_constructor_args(chain_id: int, network_name: str) -> tuple[str, str]:
    cfg = CHAIN_CONFIG.get(chain_id)
    if cfg is None:
        raise RuntimeError(
            f"No CHAIN_CONFIG entry for chain_id={chain_id} (network={network_name}). "
            f"Add one to script/deploy.py before deploying — fee_receiver and owner "
            f"are baked into the contract and cannot be changed without redeploying."
        )
    return to_checksum_address(cfg.fee_receiver), to_checksum_address(cfg.owner)


def deploy() -> VyperContract:
    network = get_active_network()
    chain_id = network.chain_id
    name = network.name

    fee_receiver, owner = _read_constructor_args(chain_id, name)

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
