// SPDX-License-Identifier: AGPL-3.0
pragma solidity 0.8.14;

interface UniswapAnchoredViewI {
    /**
     * @notice Get the underlying price of a cToken
     * @dev Implements the PriceOracle interface for Compound v2.
     * See: https://docs.compound.finance/v2/prices/#underlying-price
     * @param cToken The cToken address for price retrieval
     * @return The price of the asset in USD as an unsigned integer scaled up by 10 ^ (36 - underlying asset decimals).
     * E.g. WBTC has 8 decimal places, so the return value is scaled up by 1e28.
     */
    function getUnderlyingPrice(address cToken) external view returns (uint256);

    /**
     * @notice Get the official price for a symbol
     * @dev See: https://docs.compound.finance/v2/prices/#price
     * @param symbol The symbol to fetch the price of
     * @return The price of the asset in USD as an unsigned integer scaled up by 10 ^ 6.
     */
    function price(string memory symbol) external view returns (uint256);
}
