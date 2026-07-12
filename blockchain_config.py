from pathlib import Path
import json


GANACHE_RPC = "http://127.0.0.1:7545"

# Role-to-Ganache-account mapping for demo wallets
GANACHE_ROLE_ACCOUNT_INDEX = {
    "admin": 0,
    "doctor": 2,
    "patient": 3,
    "storage": 1,
}


# Use Account 0 from Ganache (private key from Ganache UI)
SENDER_PRIVATE_KEY = "0x35edc4276ef525804a4c1052a6de77860d9d98dafb330dee4574a7c0cb650507"


_ROOT = Path(__file__).resolve().parent
_BUILD_DIR = _ROOT / "blockchain"
_ADDRESS_FILE = _BUILD_DIR / "deployed_contract_address.txt"
_ABI_FILE = _BUILD_DIR / "health_integrity_ledger_abi.json"


CONTRACT_ADDRESS = (
    _ADDRESS_FILE.read_text(encoding="utf-8").strip()
    if _ADDRESS_FILE.exists()
    else "0xF001739188d4adEb511A078356f4Be1BBE9208f9"
)


if _ABI_FILE.exists():
    CONTRACT_ABI = json.loads(_ABI_FILE.read_text(encoding="utf-8"))
else:
    CONTRACT_ABI = [
        {
            "anonymous": False,
            "inputs": [
                {
                    "indexed": True,
                    "internalType": "address",
                    "name": "user",
                    "type": "address"
                },
                {
                    "indexed": False,
                    "internalType": "string",
                    "name": "dataHash",
                    "type": "string"
                },
                {
                    "indexed": False,
                    "internalType": "uint256",
                    "name": "versionNo",
                    "type": "uint256"
                },
                {
                    "indexed": False,
                    "internalType": "uint256",
                    "name": "timestamp",
                    "type": "uint256"
                }
            ],
            "name": "DataHashStored",
            "type": "event"
        },
        {
            "anonymous": False,
            "inputs": [
                {
                    "indexed": True,
                    "internalType": "address",
                    "name": "user",
                    "type": "address"
                },
                {
                    "indexed": False,
                    "internalType": "string",
                    "name": "payloadHash",
                    "type": "string"
                },
                {
                    "indexed": False,
                    "internalType": "uint256",
                    "name": "versionNo",
                    "type": "uint256"
                },
                {
                    "indexed": False,
                    "internalType": "uint256",
                    "name": "timestamp",
                    "type": "uint256"
                }
            ],
            "name": "PayloadHashStored",
            "type": "event"
        },
        {
            "anonymous": False,
            "inputs": [
                {
                    "indexed": True,
                    "internalType": "address",
                    "name": "user",
                    "type": "address"
                },
                {
                    "indexed": False,
                    "internalType": "string",
                    "name": "identityHash",
                    "type": "string"
                },
                {
                    "indexed": False,
                    "internalType": "uint256",
                    "name": "versionNo",
                    "type": "uint256"
                },
                {
                    "indexed": False,
                    "internalType": "uint256",
                    "name": "timestamp",
                    "type": "uint256"
                }
            ],
            "name": "IdentityHashStored",
            "type": "event"
        },
        {
            "inputs": [
                {
                    "internalType": "address",
                    "name": "_user",
                    "type": "address"
                }
            ],
            "name": "getRecords",
            "outputs": [
                {
                    "components": [
                        {
                            "internalType": "string",
                            "name": "recordHash",
                            "type": "string"
                        },
                        {
                            "internalType": "uint256",
                            "name": "timestamp",
                            "type": "uint256"
                        }
                    ],
                    "internalType": "struct HealthIntegrityLedger.RecordEntry[]",
                    "name": "",
                    "type": "tuple[]"
                }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
                {
                    "internalType": "string",
                    "name": "dataHash",
                    "type": "string"
                }
            ],
            "name": "storeDataHash",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [
                {
                    "internalType": "string",
                    "name": "payloadHash",
                    "type": "string"
                }
            ],
            "name": "storePayloadHash",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [
                {
                    "internalType": "string",
                    "name": "identityHash",
                    "type": "string"
                }
            ],
            "name": "storeIdentityHash",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [
                {
                    "internalType": "string",
                    "name": "_recordHash",
                    "type": "string"
                }
            ],
            "name": "storeRecord",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [
                {
                    "internalType": "address",
                    "name": "_user",
                    "type": "address"
                }
            ],
            "name": "getLatestRecord",
            "outputs": [
                {
                    "components": [
                        {
                            "internalType": "uint256",
                            "name": "versionNo",
                            "type": "uint256"
                        },
                        {
                            "internalType": "string",
                            "name": "recordHash",
                            "type": "string"
                        },
                        {
                            "internalType": "address",
                            "name": "updatedBy",
                            "type": "address"
                        },
                        {
                            "internalType": "uint256",
                            "name": "timestamp",
                            "type": "uint256"
                        }
                    ],
                    "internalType": "struct HealthIntegrityLedger.RecordEntry",
                    "name": "",
                    "type": "tuple"
                }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
                {
                    "internalType": "address",
                    "name": "_user",
                    "type": "address"
                }
            ],
            "name": "getLatestVersion",
            "outputs": [
                {
                    "internalType": "uint256",
                    "name": "",
                    "type": "uint256"
                }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
                {
                    "internalType": "address",
                    "name": "_user",
                    "type": "address"
                }
            ],
            "name": "getRecordCount",
            "outputs": [
                {
                    "internalType": "uint256",
                    "name": "",
                    "type": "uint256"
                }
            ],
            "stateMutability": "view",
            "type": "function"
        }
    ]
