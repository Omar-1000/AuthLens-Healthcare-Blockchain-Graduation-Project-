const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");
const Web3 = require("web3");

const ROOT = path.resolve(__dirname, "..", "..");
const SOURCE_PATH = path.join(ROOT, "contracts", "HealthIntegrityLedger.sol");
const BLOCKCHAIN_DIR = path.join(ROOT, "blockchain");
const ABI_PATH = path.join(BLOCKCHAIN_DIR, "health_integrity_ledger_abi.json");
const LEGACY_ABI_PATH = path.join(BLOCKCHAIN_DIR, "contract_abi.json");
const ADDRESS_PATH = path.join(BLOCKCHAIN_DIR, "deployed_contract_address.txt");

const GANACHE_RPC = "http://127.0.0.1:7545";
const SOLC_EXE = path.join(process.env.USERPROFILE || "", ".solcx", "solc-v0.8.19", "solc.exe");

function ensureDir(dirPath) {
  if (!fs.existsSync(dirPath)) {
    fs.mkdirSync(dirPath, { recursive: true });
  }
}

function compileContract(source) {
  const input = {
    language: "Solidity",
    sources: {
      "HealthIntegrityLedger.sol": { content: source },
    },
    settings: {
      optimizer: { enabled: true, runs: 200 },
      outputSelection: {
        "*": {
          "*": ["abi", "evm.bytecode.object", "evm.deployedBytecode.object"],
        },
      },
    },
  };

  if (!fs.existsSync(SOLC_EXE)) {
    throw new Error(`Solidity compiler not found at ${SOLC_EXE}`);
  }

  const compiled = execFileSync(SOLC_EXE, ["--standard-json"], {
    input: JSON.stringify(input),
    encoding: "utf8",
    maxBuffer: 50 * 1024 * 1024,
  });

  const output = JSON.parse(compiled);
  if (output.errors && output.errors.length) {
    const seriousErrors = output.errors.filter((item) => item.severity === "error");
    output.errors.forEach((item) => {
      console.log(item.formattedMessage || item.message);
    });
    if (seriousErrors.length) {
      throw new Error("Solidity compilation failed");
    }
  }

  const contractData = output.contracts["HealthIntegrityLedger.sol"]["HealthIntegrityLedger"];
  if (!contractData) {
    throw new Error("Compiled contract data was not found");
  }

  return contractData;
}

async function main() {
  ensureDir(BLOCKCHAIN_DIR);

  const source = fs.readFileSync(SOURCE_PATH, "utf8");
  const contractData = compileContract(source);
  const abi = contractData.abi;
  const bytecode = contractData.evm.bytecode.object;
  const deployedBytecode = contractData.evm.deployedBytecode.object;

  fs.writeFileSync(ABI_PATH, JSON.stringify(abi, null, 2), "utf8");
  fs.writeFileSync(LEGACY_ABI_PATH, JSON.stringify(abi, null, 2), "utf8");

  const web3 = new Web3(GANACHE_RPC);
  const connected = await web3.eth.net.isListening();
  if (!connected) {
    throw new Error("Not connected to Ganache");
  }

  const accounts = await web3.eth.getAccounts();
  if (!accounts.length) {
    throw new Error("No Ganache accounts available");
  }

  const sender = accounts[0];
  const gasPrice = await web3.eth.getGasPrice();
  const contract = new web3.eth.Contract(abi);

  const deployed = await contract.deploy({
    data: `0x${bytecode}`,
  }).send({
    from: sender,
    gas: 2_500_000,
    gasPrice,
  });

  const address = deployed.options.address;
  fs.writeFileSync(ADDRESS_PATH, address, "utf8");

  const truffleArtifactPath = path.join(ROOT, "truffle-ledger", "build", "contracts", "HealthIntegrityLedger.json");
  if (fs.existsSync(truffleArtifactPath)) {
    const artifact = JSON.parse(fs.readFileSync(truffleArtifactPath, "utf8"));
    artifact.abi = abi;
    artifact.bytecode = bytecode;
    artifact.deployedBytecode = deployedBytecode;
    artifact.networks = artifact.networks || {};
    artifact.networks["development"] = {
      events: {},
      links: {},
      address,
      transactionHash: "",
    };
    fs.writeFileSync(truffleArtifactPath, JSON.stringify(artifact, null, 2), "utf8");
  }

  console.log(address);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
