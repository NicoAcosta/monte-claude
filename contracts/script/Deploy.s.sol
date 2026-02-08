// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script, console} from "forge-std/Script.sol";
import {Escrow} from "../src/Escrow.sol";
import {EscrowFactory} from "../src/EscrowFactory.sol";

contract Deploy is Script {
    function run() external {
        vm.startBroadcast();

        Escrow impl = new Escrow();
        console.log("Escrow implementation:", address(impl));

        EscrowFactory factory = new EscrowFactory(address(impl));
        console.log("EscrowFactory:", address(factory));

        vm.stopBroadcast();
    }
}
