from web3 import Web3
from blockchain_config import GANACHE_RPC, CONTRACT_ADDRESS, CONTRACT_ABI, GANACHE_ROLE_ACCOUNT_INDEX


w3 = Web3(Web3.HTTPProvider(GANACHE_RPC))


def _build_contract():
    return w3.eth.contract(
        address=Web3.to_checksum_address(CONTRACT_ADDRESS),
        abi=CONTRACT_ABI
    )


def _store_named_hash_onchain(method_name: str, hash_value: str, sender_role=None, sender_address=None) -> str:
    if not w3.is_connected():
        raise RuntimeError("Not connected to Ganache")

    sender = resolve_sender_address(sender_role=sender_role, sender_address=sender_address)

    nonce = w3.eth.get_transaction_count(sender)
    contract = _build_contract()
    contract_method = getattr(contract.functions, method_name, None)
    if contract_method is None:
        raise RuntimeError(f"Contract method {method_name} is not available in the loaded ABI")

    txn = contract_method(hash_value).build_transaction({
        "from": sender,
        "nonce": nonce,
        "gas": 300000,
        "gasPrice": w3.eth.gas_price,
    })

    tx_hash = w3.eth.send_transaction(txn)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt.status != 1:
        raise RuntimeError("On-chain record write reverted")

    return w3.to_hex(tx_hash)


def resolve_sender_address(sender_role=None, sender_address=None):
    accounts = w3.eth.accounts
    if sender_address and Web3.is_address(sender_address):
        checksum = Web3.to_checksum_address(sender_address)
        if checksum in accounts:
            return checksum

    if sender_role in GANACHE_ROLE_ACCOUNT_INDEX:
        idx = GANACHE_ROLE_ACCOUNT_INDEX[sender_role]
        if len(accounts) > idx:
            return accounts[idx]

    if accounts:
        return accounts[0]

    raise RuntimeError("No unlocked Ganache accounts found")


def store_data_hash_onchain(data_hash: str, sender_role=None, sender_address=None) -> str:
    return _store_named_hash_onchain("storeDataHash", data_hash, sender_role=sender_role, sender_address=sender_address)


def store_payload_hash_onchain(payload_hash: str, sender_role=None, sender_address=None) -> str:
    return _store_named_hash_onchain("storePayloadHash", payload_hash, sender_role=sender_role, sender_address=sender_address)


def store_identity_hash_onchain(identity_hash: str, sender_role=None, sender_address=None) -> str:
    return _store_named_hash_onchain("storeIdentityHash", identity_hash, sender_role=sender_role, sender_address=sender_address)


def store_record_onchain(record_hash: str, sender_role=None, sender_address=None) -> str:
    return store_payload_hash_onchain(record_hash, sender_role=sender_role, sender_address=sender_address)


def get_latest_record_hash(user_address: str):
    if not w3.is_connected():
        raise RuntimeError("Not connected to Ganache")
    if not user_address or not Web3.is_address(user_address):
        raise ValueError("Invalid wallet address")

    contract = _build_contract()
    latest_record = contract.functions.getLatestRecord(Web3.to_checksum_address(user_address)).call()
    if not latest_record:
        return None

    record_hash = latest_record[1] if len(latest_record) > 1 else None
    return record_hash or None
