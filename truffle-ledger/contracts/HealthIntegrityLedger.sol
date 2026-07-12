// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

contract HealthIntegrityLedger {
    struct RecordEntry {
        uint256 versionNo;
        string recordHash;
        address updatedBy;
        uint256 timestamp;
    }

    mapping(address => RecordEntry[]) private _records;
    mapping(address => uint256) private _latestVersion;

    event DataHashStored(
        address indexed user,
        string dataHash,
        uint256 versionNo,
        uint256 timestamp
    );

    event PayloadHashStored(
        address indexed user,
        string payloadHash,
        uint256 versionNo,
        uint256 timestamp
    );

    event IdentityHashStored(
        address indexed user,
        string identityHash,
        uint256 versionNo,
        uint256 timestamp
    );

    function _storeHash(string memory _hashValue) private returns (uint256 newVersion, uint256 ts) {
        newVersion = _latestVersion[msg.sender] + 1;
        ts = block.timestamp;

        _records[msg.sender].push(
            RecordEntry({
                versionNo: newVersion,
                recordHash: _hashValue,
                updatedBy: msg.sender,
                timestamp: ts
            })
        );

        _latestVersion[msg.sender] = newVersion;
    }

    function storeDataHash(string memory dataHash) external {
        (uint256 newVersion, uint256 ts) = _storeHash(dataHash);
        emit DataHashStored(msg.sender, dataHash, newVersion, ts);
    }

    function storePayloadHash(string memory payloadHash) external {
        (uint256 newVersion, uint256 ts) = _storeHash(payloadHash);
        emit PayloadHashStored(msg.sender, payloadHash, newVersion, ts);
    }

    function storeIdentityHash(string memory identityHash) external {
        (uint256 newVersion, uint256 ts) = _storeHash(identityHash);
        emit IdentityHashStored(msg.sender, identityHash, newVersion, ts);
    }

    function storeRecord(string memory _recordHash) external {
        (uint256 newVersion, uint256 ts) = _storeHash(_recordHash);
        emit PayloadHashStored(msg.sender, _recordHash, newVersion, ts);
    }

    function getRecords(address _user) external view returns (RecordEntry[] memory) {
        RecordEntry[] storage stored = _records[_user];
        RecordEntry[] memory result = new RecordEntry[](stored.length);

        for (uint256 i = 0; i < stored.length; i++) {
            result[i] = stored[i];
        }

        return result;
    }

    function getLatestRecord(address _user) external view returns (RecordEntry memory) {
        RecordEntry[] storage stored = _records[_user];
        require(stored.length > 0, "No records stored");
        return stored[stored.length - 1];
    }

    function getLatestVersion(address _user) external view returns (uint256) {
        return _latestVersion[_user];
    }

    function getRecordCount(address _user) external view returns (uint256) {
        return _records[_user].length;
    }
}
