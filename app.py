import asyncio
from asyncio import Semaphore
from prompt_toolkit.shortcuts import radiolist_dialog, input_dialog
from prompt_toolkit.styles import Style

from random import uniform

from tasks.hyperlend import Hyperlend
from eth_async.client import Client
from eth_async.data.models import Networks, TokenAmount
from utils import logger, format_proxy, load_file


async def process_wallet(private_key: str, proxy: str, api_key: str, semaphore: Semaphore, selected_function: str):
    """
        Processes a wallet using the provided private key, proxy, and selected function.

        This function interacts with the HyperEVM network to execute the specified
        function, such as claiming faucet, checking balance, swapping tokens, etc.

        Args:
            private_key (str): The private key of the wallet to interact with.
            proxy (str): The proxy settings to use for the connection.
            api_key (str): The API key for Capmonster service.
            semaphore (Semaphore): The semaphore to control concurrent execution.
            selected_function (str): The selected function to execute. Valid options:
                - ???? -

        Returns:
            None: This function performs an action but does not return a value.
    """
    async with semaphore:
        client = Client(private_key=private_key,
                        network=Networks.Hyperlend,
                        proxy=proxy)
        proxy_dict = format_proxy(proxy)

        hyperlend = Hyperlend(client=client,
                              api_key=api_key,
                              proxy_info=proxy_dict)

        if selected_function == 'claim_hype_faucet':
            await hyperlend.claim_hype_faucet()
        # elif selected_function == 'get_balances':
        #     await Hyperlend.get_balances()
        elif selected_function == 'claim_mbtc_faucet':
            await hyperlend.claim_mbtc_faucet()
        elif selected_function == 'supply_mbtc':
            await hyperlend.supply_mbtc(amount=TokenAmount(amount=round(uniform(0.01, 0.02), 4), decimals=8))
        elif selected_function == 'supply_eth':
            await hyperlend.supply_eth(amount=TokenAmount(amount=round(uniform(0.0001, 0.0005), 5)))
        elif selected_function == 'supply_hype':
            await hyperlend.supply_hype(amount=TokenAmount(amount=round(uniform(0.0001, 0.0005), 5)))


async def main():
    try:
        max_concurrent_tasks = await input_dialog(
            title="Configure threads",
            text="Enter the number of threads:"
        ).run_async()

        if not max_concurrent_tasks or not max_concurrent_tasks.isdigit() or int(max_concurrent_tasks) <= 0:
            logger.error("An incorrect value has been entered. Use the default value: 1.")
            max_concurrent_tasks = 1
        else:
            max_concurrent_tasks = int(max_concurrent_tasks)

    except Exception as e:
        logger.error(f"Error when entering the number of threads: {e}. Use default value: 1.")
        max_concurrent_tasks = 1

    semaphore: Semaphore = Semaphore(max_concurrent_tasks)

    proxies = load_file("./proxies.txt", 'proxy')
    api_key = load_file("./api_key.txt", 'API-key of Capmonster')
    private_keys = load_file("./private_keys.txt", 'wallet')

    if not api_key:
        logger.error("API key from Capmonster was not found.")
        return

    if not proxies:
        logger.error("Proxies not found.")
        return

    if not private_keys:
        logger.error("Private keys not found.")
        return

    if len(private_keys) != len(proxies):
        logger.error('Not equal number of proxies and wallets.')
        return

    style = Style.from_dict({
        'selected': 'bg:#00aaaa #ffffff',
        'pointer': '#00aaaa bold',
    })

    functions = [
        ('claim_hype_faucet', 'Claim HYPE Faucet'),
        # ('get_balances', 'Get token balances'),
        ('claim_mbtc_faucet', 'Claim MBTC Faucet'),
        ('supply_mbtc', 'Supply MBTC'),
        ('supply_eth', 'Supply ETH'),
        ('supply_hype', 'Supply HYPE'),
    ]

    selected_function = await radiolist_dialog(
        'Select the function to perform:',
        values=functions,
        style=style
    ).run_async()

    tasks = []

    for i in range(len(private_keys)):
        tasks.append(
            asyncio.create_task(
                process_wallet(
                    private_key=private_keys[i],
                    proxy=proxies[i],
                    api_key=api_key[0],
                    semaphore=semaphore,
                    selected_function=selected_function
                )
            ))

    await asyncio.gather(*tasks)


if __name__ == '__main__':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        # Try to get the running event loop
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # If no loop is running, create a new one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
    else:
        # If a loop is already running, schedule the coroutine
        loop.create_task(main())
