from ape import reverts
import pytest
from utils.constants import ZERO_ADDRESS


def test_reward_yswap(
    asset,
    ctoken,
    user,
    create_vault_and_strategy,
    gov,
    strategist,
    amount,
    provide_strategy_with_debt,
    comp,
    comp_whale,
    trade_factory,
    ymechs_safe,
):
    vault, strategy = create_vault_and_strategy(gov, amount)
    new_debt = amount
    provide_strategy_with_debt(gov, strategy, vault, new_debt)

    trade_factory.grantRole(
        trade_factory.STRATEGY(), strategy.address, sender=ymechs_safe
    )

    before_bal = strategy.totalAssets()

    reward = 2 * 10 ** comp.decimals()
    comp.transfer(strategy, reward, sender=comp_whale)
    assert comp.balanceOf(strategy) == reward

    with reverts():
        strategy.setTradeFactory(trade_factory.address, sender=user)

    assert strategy.tradeFactory() == ZERO_ADDRESS
    strategy.setTradeFactory(trade_factory.address, sender=strategist)
    assert strategy.tradeFactory() == trade_factory.address

    # harvest function will not sell COMP because yswap is set
    strategy.harvest(sender=strategist)
    assert comp.balanceOf(strategy) == reward

    token_in = comp
    token_out = asset
    amount_in = reward
    asyncTradeExecutionDetails = [
        strategy.address,
        token_in.address,
        token_out.address,
        amount_in,
        1,
    ]

    # encode path
    # path = [token_in.address, weth.address, token_out.address]
    # Code in Solidity used to generate path_in_bytes:
    # address[] memory path = new address[](3);
    # path[0] = 0xc00e94Cb662C3520282E6f5717214004A7f26888; # COMP
    # path[1] = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2; # WETH
    # path[2] = token.address;
    # return abi.encode(path);
    path_in_bytes = (
        "0x00000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000000000000000003000000000000000000000000c00e94cb662c3520282e6f5717214004a7f26888000000000000000000000000c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2000000000000000000000000"
        + token_out.address[2:]
    )

    # Trigger ySwap
    tx_swap = trade_factory.execute(
        asyncTradeExecutionDetails,
        "0x408Ec47533aEF482DC8fA568c36EC0De00593f44",
        path_in_bytes,
        sender=ymechs_safe,
    )
    tx_swap.return_value > 0

    # rewards should be claimed
    assert strategy.totalAssets() > before_bal
    assert comp.balanceOf(strategy) == 0
