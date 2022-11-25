// SPDX-License-Identifier: GPL-3.0
pragma solidity 0.8.14;

interface TestITradeFactory {
    struct AsyncTradeExecutionDetails {
        address _strategy;
        address _tokenIn;
        address _tokenOut;
        uint256 _amount;
        uint256 _minAmountOut;
    }
    function enable(address _tokenIn, address _tokenOut) external;
    function execute(
        AsyncTradeExecutionDetails calldata _tradeExecutionDetails,
        address _swapper,
        bytes calldata _data
    ) external returns (uint256 _receivedAmount);

    function grantRole(bytes32 role, address account) external;

    function STRATEGY() external view returns (bytes32);
}
