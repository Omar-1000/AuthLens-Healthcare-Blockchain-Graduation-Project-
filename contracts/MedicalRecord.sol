// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract MedicalRecord {
    struct Record {
        string recordHash;
        uint256 timestamp;
    }

    mapping(address => Record[]) private _records;

    event RecordStored(address indexed user, string recordHash, uint256 timestamp);

    function storeRecord(string memory _recordHash) external {
        uint256 ts = block.timestamp;
        _records[msg.sender].push(Record({recordHash: _recordHash, timestamp: ts}));
        emit RecordStored(msg.sender, _recordHash, ts);
    }

    function getRecords(address _user) external view returns (Record[] memory) {
        Record[] storage stored = _records[_user];
        Record[] memory result = new Record[](stored.length);

        for (uint256 i = 0; i < stored.length; i++) {
            result[i] = stored[i];
        }

        return result;
    }
}
