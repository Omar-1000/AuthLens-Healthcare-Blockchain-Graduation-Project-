const HealthIntegrityLedger = artifacts.require("HealthIntegrityLedger");

module.exports = function (deployer) {
  deployer.deploy(HealthIntegrityLedger);
};
