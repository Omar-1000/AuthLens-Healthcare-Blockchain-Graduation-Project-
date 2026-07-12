from pathlib import Path
import json
import sys

from solcx import compile_standard, install_solc
from web3 import Web3
ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "contracts" / "HealthIntegrityLedger.sol"
BUILD_DIR = ROOT / "blockchain"
BUILD_DIR.mkdir(exist_ok=True)

GANACHE_RPC = "http://127.0.0.1:7545"
SOLC_VERSION = "0.8.19"


def main():
    install_solc(SOLC_VERSION)

    source = SOURCE_PATH.read_text(encoding="utf-8")
    compiled = compile_standard(
        {
            "language": "Solidity",
            "sources": {"HealthIntegrityLedger.sol": {"content": source}},
            "settings": {
                "evmVersion": "paris",
                "outputSelection": {
                    "*": {
                        "*": ["abi", "evm.bytecode.object"]
                    }
                }
            },
        },
        solc_version=SOLC_VERSION,
    )

    contract_data = compiled["contracts"]["HealthIntegrityLedger.sol"]["HealthIntegrityLedger"]
    abi = contract_data["abi"]
    bytecode = contract_data["evm"]["bytecode"]["object"]

    abi_path = BUILD_DIR / "health_integrity_ledger_abi.json"
    abi_path.write_text(json.dumps(abi, indent=2), encoding="utf-8")

    w3 = Web3(Web3.HTTPProvider(GANACHE_RPC))
    if not w3.is_connected():
        raise RuntimeError("Not connected to Ganache")

    accounts = w3.eth.accounts
    if not accounts:
        raise RuntimeError("No Ganache accounts available")

    sender = accounts[0]
    contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    nonce = w3.eth.get_transaction_count(sender)
    txn = contract.constructor().build_transaction(
        {
            "from": sender,
            "nonce": nonce,
            "gas": 2_500_000,
            "gasPrice": w3.eth.gas_price,
        }
    )
    tx_hash = w3.eth.send_transaction(txn)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    address_path = BUILD_DIR / "deployed_contract_address.txt"
    address_path.write_text(receipt.contractAddress, encoding="utf-8")

    print(receipt.contractAddress)


if __name__ == "__main__":
    main()
