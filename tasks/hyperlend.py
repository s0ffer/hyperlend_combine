import asyncio
import random
import time
from decimal import Decimal

from web3.exceptions import ContractLogicError
from web3.types import TxParams
from capmonstercloudclient import CapMonsterClient, ClientOptions
from capmonstercloudclient.requests import TurnstileRequest
import httpx

from data.models import Contracts
from eth_async.data.models import TokenAmount, TxArgs
from eth_async.utils.utils import randfloat
from tasks.base import Base
from utils import logger


class Hyperlend(Base):

    async def claim_hype_faucet(self) -> None:
        """
            Claims tokens from the Hyperlend faucet.

            This function interacts with the Hyperlend faucet API, solves the CAPTCHA using
            CapMonster, and then sends a request to claim tokens. It logs the status of each
            step and handles errors such as insufficient balance or time restrictions.

            Steps:
                1. Initialize CapMonsterClient with the provided API key.
                2. Solve the CAPTCHA using the Turnstile request.
                3. Send an OPTIONS request to the faucet's API to claim tokens.
                4. Send a POST request with the CAPTCHA token for token claim.
                5. Handle response errors and successful faucet claims.
                6. Log the results of the claim request (success or error).

            Notes:
                - This function requires a valid API key for CapMonster and a working
                  proxy setup for the faucet request.
                - The response handling checks for two types of errors: insufficient balance
                  and time restrictions on claiming.
                - Logs various stages of the process to track the claim status.
        """
        faucet_url = 'https://testnet.hyperlend.finance/dashboard'
        website_key = '0x4AAAAAAA2Qg1SB87LOUhrG'
        logger.info(f'Starting HYPE faucet claim | {self.client.account.address}')

        client_options = ClientOptions(api_key=str(self.api_key[0]))
        cap_monster_client = CapMonsterClient(options=client_options)

        turnstile_request = TurnstileRequest(
            websiteURL=faucet_url,
            websiteKey=website_key,
            proxyType='http',
            proxyAddress=str(self.proxy_info.get('ip')),
            proxyPort=int(self.proxy_info.get('port')),
            proxyLogin=str(self.proxy_info.get('username')),
            proxyPassword=str(self.proxy_info.get('password'))
        )
        responses = await cap_monster_client.solve_captcha(turnstile_request)
        logger.info(f'Received CAPTCHA response from Capmonster | {self.client.account.address}')
        solution = responses['token']
        logger.info(f'Sending claim request | {self.client.account.address}')

        async with httpx.AsyncClient(proxy=self.client.proxy) as client:
            headers = {
                'accept': '*/*',
                'accept-language': 'ru,en-US;q=0.9,en;q=0.8,ja;q=0.7,kk;q=0.6,fr;q=0.5',
                'content-type': 'application/json',
                'dnt': '1',
                'origin': 'https://testnet.hyperlend.finance',
                'priority': 'u=1, i',
                'referer': 'https://testnet.hyperlend.finance/',
                'sec-ch-ua': '"Not A(Brand";v="8", "Chromium";v="132", "Google Chrome";v="132"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-site',
                'user-agent': self.random_useragent,
            }

            json_data = {
                'type': 'ethFaucet',
                'user': self.client.account.address,
                'challenge': solution,
                'challengeV2': 'If you are running the farming bot, stop wasting your time. Testnet will not be '
                               'directly incentivized, and mainnet airdrop will be linear with a minimum threshold.',
            }

            response = await client.post('https://api.hyperlend.finance/ethFaucet',
                                         headers=headers,
                                         json=json_data)

        result = response.json()
        msg = result.get("response", "")
        if isinstance(msg, dict) and msg.get('status') == 1:
            logger.success(f'Claimed native tokens | {self.client.account.address} | '
                           f'{round((await self.client.wallet.balance()).Ether, 6)} HYPE')
        elif 'user_already_claimed' in msg:
            logger.error(f'Already claimed, once per wallet! | {self.client.account.address} | '
                         f'{round((await self.client.wallet.balance()).Ether, 6)} HYPE')
        else:
            logger.error(f'{msg} | {self.client.account.address} | '
                         f'{round((await self.client.wallet.balance()).Ether, 6)} HYPE')

    async def claim_mbtc_faucet(self) -> None:
        logger.info(f'Starting MBTC faucet claim | {self.client.account.address}')

        failed_text = f'Failed to claim MBTC faucet'

        tx_params = TxParams(
            to=Contracts.HYPERLEND_FAUCET.address,
            data='0x4e71d92d' # Claim()
        )

        try:
            tx = await self.client.transactions.sign_and_send(tx_params=tx_params)

            if tx is None:
                logger.error(f'{failed_text}! | {self.client.account.address}')
                return

            receipt = await tx.wait_for_receipt(client=self.client, timeout=300)
            if receipt:
                logger.success(
                    f'0.1 MBTC claimed | {tx.hash.hex()} | {self.client.account.address}')
                return

            logger.error(f'{failed_text}! | {self.client.account.address}')

        except ContractLogicError as e:
            if "already claimed" in str(e):
                logger.warning(f'Already claimed MBTC faucet | {self.client.account.address}')
            else:
                logger.error(f"{e} | {self.client.account.address}")
        except Exception as e:
            logger.error(f"{e} | {self.client.account.address}")


    async def swap_bera_to_ibgt(self) -> None:
        """
            Swaps BERA tokens for IBGT tokens via the Kodiak contract.

            This function performs the following steps:
            1. Checks if the user has enough BERA balance to perform the swap (adding a buffer of 0.15 BERA).
            2. Calculates the amount of IBGT that will be received from the swap.
            3. Constructs the transaction parameters for the swap.
            4. Signs and sends the transaction to the Kodiak contract.
            5. Waits for the transaction receipt and logs the success or failure.
        """
        logger.info(f'Starting swap of BERA to IBGT | {self.client.account.address}')

        failed_text = f'Failed to swap BERA to iBGT via Kodiak'

        amount = TokenAmount(amount=randfloat(from_=0.4, to_=0.43, step=0.01),
                             decimals=18,
                             wei=False)

        balance = await self.client.wallet.balance()
        required_balance = amount.Ether + Decimal('0.15')

        if balance.Ether < required_balance:
            logger.error(
                f'Insufficient balance {round(balance.Ether, 2)} BERA | Needed {amount.Ether} BERA | '
                f'{self.client.account.address}')
            return

        contract = await self.client.contracts.get(contract_address=Contracts.KODIAK)

        amount_out_min = await self.get_amount_out(amount=amount)

        exact_input_single_params = TxArgs(
            params=TxArgs(
                tokenIn=Contracts.WBERA.address,
                tokenOut=Contracts.iBGT.address,
                fee=500,
                recipient=self.client.account.address,
                amountIn=amount.Wei,
                amountOutMinimum=int(amount_out_min.Wei * 0.995),
                sqrtPriceLimitX96=0
            ).tuple()
        )

        exact_input_single_data = contract.encodeABI('exactInputSingle', args=exact_input_single_params.tuple())
        exact_input_single_data += '0' * 56
        params = TxArgs(
            deadline=int(time.time() + 20 * 60),
            data=[exact_input_single_data]
        )

        data = contract.encodeABI('multicall', args=params.tuple())

        # Changing 100 на 0e4 before 04e45aff in tx hash, like in UI.
        updated_data = data.replace("10004e45aaf", "0e404e45aaf")

        tx_params = TxParams(
            to=contract.address,
            data=updated_data,
            value=amount.Wei,
        )

        tx = await self.client.transactions.sign_and_send(tx_params=tx_params)

        if tx is None:
            return
        else:
            receipt = await tx.wait_for_receipt(client=self.client, timeout=300)
            if receipt:
                logger.success(
                    f'{amount.Ether} BERA swapped to {round(amount_out_min.Ether, 2)} '
                    f'iBGT via Kodiak: {tx.hash.hex()} | {self.client.account.address}')
                return
            logger.error(f'{failed_text}! | {self.client.account.address}')
    #
    # async def deposit_ibgt_bera(self) -> None:
    #     """
    #         Deposits BERA and iBGT tokens into the Kodiak liquidity pool.
    #
    #         This function performs the following steps: 1. Fetches the user's balance of iBGT tokens and determines
    #         the amount to deposit. 2. Checks if the user has enough BERA tokens to match the required amount for
    #         liquidity. 3. Approves the Island router contract to spend iBGT tokens. 4. Calculates the amount of
    #         shares to mint by calling the `getMintAmounts` function on the Kodiak vault contract. 5. Encodes and
    #         sends the transaction to add liquidity to the pool using the Island router contract. 6. Waits for the
    #         transaction receipt and logs success or failure.
    #     """
    #     logger.info(f'Starting deposit of iBGT-BERA | {self.client.account.address}')
    #
    #     failed_text = f'Failed to make deposit into iBGT-BERA pool via Kodiak | {self.client.account.address}'
    #
    #     amount_0_max_ibgt = await self.client.wallet.balance(token=Contracts.iBGT)
    #
    #     if amount_0_max_ibgt.Ether > 0.12:
    #         amount_0_max_ibgt = TokenAmount(amount=randfloat(0.11, 0.14, 0.01))
    #
    #     if amount_0_max_ibgt.Wei <= 0:
    #         logger.error(f'No iBGT for deposit | {self.client.account.address}')
    #         return
    #
    #     amount_1_max_bera = await self.get_amount_out(amount=amount_0_max_ibgt, to_ibgt=False)
    #
    #     balance = await self.client.wallet.balance()
    #
    #     if balance.Wei < amount_1_max_bera.Wei:
    #         logger.error(f'Insufficient BERA balance for pool | {self.client.account.address}')
    #         return
    #
    #     if await self.approve_interface(token_address=Contracts.iBGT.address,
    #                                     spender=Contracts.ISLAND_ROUTER.address,
    #                                     amount=amount_0_max_ibgt,
    #                                     max=True
    #                                     ):
    #         logger.info(f'Approved iBGT for router pool | {self.client.account.address}')
    #     else:
    #         logger.error('Failed to approve iBGT')
    #         return
    #
    #     island_router = await self.client.contracts.get(contract_address=Contracts.ISLAND_ROUTER)
    #     kodiak_vault = await self.client.contracts.get(contract_address=Contracts.KODIAK_VAULT)
    #     shares_amount = (await kodiak_vault.functions.getMintAmounts(
    #         amount_0_max_ibgt.Wei,
    #         amount_1_max_bera.Wei).call())[2]
    #
    #     amount_0_min_ibgt = int(amount_0_max_ibgt.Wei / 1.01010101)
    #     amount_1_min_bera = int(amount_1_max_bera.Wei / 1.01010101)
    #
    #     params = TxArgs(
    #         island=Contracts.KODIAK_VAULT.address,
    #         amount0Max=amount_0_max_ibgt.Wei,
    #         amount1Max=amount_1_max_bera.Wei,
    #         amount0Min=amount_0_min_ibgt,
    #         amount1Min=amount_1_min_bera,
    #         amountSharesMin=shares_amount,
    #         receiver=self.client.account.address
    #     )
    #
    #     data = island_router.encodeABI('addLiquidityNative', args=params.tuple())
    #
    #     tx_params = TxParams(
    #         to=island_router.address,
    #         data=data,
    #         value=amount_1_max_bera.Wei,
    #     )
    #
    #     tx = await self.client.transactions.sign_and_send(tx_params=tx_params)
    #
    #     if tx is None:
    #         return
    #     else:
    #         receipt = await tx.wait_for_receipt(client=self.client, timeout=300)
    #         if receipt:
    #             logger.success(
    #                 f'{round(amount_1_max_bera.Ether, 2)} BERA and {round(amount_0_max_ibgt.Ether, 2)}'
    #                 f' iBGT deposited into Kodiak liquidity pool: {tx.hash.hex()} | {self.client.account.address}')
    #             return
    #         logger.error(f'{failed_text}! | {self.client.account.address}')
    #
    # async def deposit_to_ibgt_wbera_station(self) -> None:
    #     """
    #         Deposits KODIAK-10 tokens into the IBGT-WBERA pool via Bartio Station.
    #
    #         This function performs the following steps:
    #         1. Fetches the user's balance of KODIAK-10 tokens.
    #         2. Checks if the user has sufficient KODIAK-10 tokens (more than 0.05 tokens).
    #         3. Approves the Bartio Station contract to spend KODIAK-10 tokens.
    #         4. Encodes and sends the transaction to stake the tokens in the IBGT-WBERA pool
    #             via the Bartio Station contract.
    #         5. Waits for the transaction receipt and logs success or failure.
    #     """
    #     logger.info(f'Starting deposit into iBGT-WBERA Station | {self.client.account.address}')
    #
    #     failed_text = (f'Failed to make deposit into iBGT-WBERA pool via Bartio Station | '
    #                    f'{self.client.account.address}')
    #
    #     amount_kodiak_10 = await self.client.wallet.balance(token=Contracts.KODIAK_VAULT)
    #
    #     if amount_kodiak_10.Ether <= 0 or amount_kodiak_10.Ether <= 0.05:
    #         logger.error(f'No or insufficient KODIAK-10 for deposit | {self.client.account.address}')
    #         return
    #
    #     if await self.approve_interface(token_address=Contracts.KODIAK_VAULT.address,
    #                                     spender=Contracts.BARTIO_STATION.address,
    #                                     amount=amount_kodiak_10,
    #                                     station_max=True
    #                                     ):
    #         logger.info(f'Approved KODIAK-10 for router pool | {self.client.account.address}')
    #     else:
    #         logger.error('Failed to approve KODIAK-10')
    #         return
    #
    #     bartio_station = await self.client.contracts.get(contract_address=Contracts.BARTIO_STATION)
    #
    #     params = TxArgs(
    #         amount=int(amount_kodiak_10.Wei * 0.999)
    #     )
    #
    #     tx_params = TxParams(
    #         to=bartio_station.address,
    #         data=bartio_station.encodeABI('stake', args=params.tuple())
    #     )
    #     tx = await self.client.transactions.sign_and_send(tx_params=tx_params)
    #
    #     if tx is None:
    #         return
    #     else:
    #         receipt = await tx.wait_for_receipt(client=self.client, timeout=300)
    #         if receipt:
    #             logger.success(f'{round(amount_kodiak_10.Ether, 2)} KODIAK-10 deposited into Bartio Station: '
    #                            f'{tx.hash.hex()} | {self.client.account.address}')
    #             return
    #         logger.error(f'{failed_text}! | {self.client.account.address}')
    #
    # async def get_bgt_reward(self) -> None:
    #     """
    #         Claims BGT rewards from the Bartio Station for the user's active deposits.
    #
    #         This function performs the following steps:
    #         1. Fetches the user's balance of active deposits in the Bartio Station contract.
    #         2. If the user has no active deposits, it logs an error and exits.
    #         3. Calls the `getReward` function of the Bartio Station contract to claim BGT rewards.
    #         4. Waits for the transaction receipt and logs success or failure.
    #         5. If the transaction is successful, it logs the amount of BGT claimed.
    #     """
    #     logger.info(f'Starting BGT claim | {self.client.account.address}')
    #
    #     failed_text = (f'Failed to claim BGT via Bartio Station | '
    #                    f'{self.client.account.address}')
    #
    #     bartio_station = await self.client.contracts.get(contract_address=Contracts.BARTIO_STATION)
    #
    #     station_balance = await bartio_station.functions.balanceOf(self.client.account.address).call()
    #
    #     if station_balance <= 0:
    #         logger.error(f'No active deposits for claiming BGT | {self.client.account.address}')
    #         return
    #
    #     params = TxArgs(
    #         address=f'{self.client.account.address}'
    #     )
    #
    #     tx_params = TxParams(
    #         to=bartio_station.address,
    #         data=bartio_station.encodeABI('getReward', args=params.tuple())
    #     )
    #     tx = await self.client.transactions.sign_and_send(tx_params=tx_params)
    #
    #     bgt_balance_before = await self.client.wallet.balance(token=Contracts.BGT)
    #
    #     if tx is None:
    #         logger.error(f'{failed_text}! | {self.client.account.address}')
    #         return
    #     else:
    #         receipt = await tx.wait_for_receipt(client=self.client, timeout=300)
    #         if receipt:
    #             await asyncio.sleep(5)
    #             bgt_balance_after = await self.client.wallet.balance(token=Contracts.BGT)
    #
    #             if bgt_balance_after.Wei > bgt_balance_before.Wei:
    #                 claim_amount = TokenAmount(bgt_balance_after.Wei - bgt_balance_before.Wei, wei=True)
    #                 logger.success(f'Claimed {claim_amount.Ether} BGT | '
    #                                f'{tx.hash.hex()} | {self.client.account.address}')
    #         else:
    #             logger.error(f'{failed_text}! | {self.client.account.address}')
    #
    # async def delegate_bgt_to_validator(self) -> None:
    #     """
    #         Delegates BGT tokens to a validator.
    #
    #         This function performs the following steps:
    #         1. Fetches the user's BGT balance.
    #         2. If the user has no BGT, it logs an error and exits.
    #         3. Retrieves the list of available validators.
    #         4. Calculates the available amount of BGT for delegation, excluding previously queued or deposited amounts.
    #         5. If there is no available BGT to delegate, it logs an error and exits.
    #         6. Selects a random validator from the list and prepares the delegation transaction.
    #         7. Sends the transaction and waits for the receipt.
    #         8. Logs success or failure based on the transaction result.
    #
    #         Notes:
    #         - The function selects a random validator from the list of available validators.
    #         - The transaction is sent with a timeout of 5 minutes.
    #         - The function ensures that the user has sufficient BGT for delegation before proceeding.
    #         - The amount delegated is calculated as 99.5% of the available BGT balance to avoid errors.
    #     """
    #     logger.info(f'Staring delegation | {self.client.account.address}')
    #
    #     failed_text = (f'Failed to delegate BGT | '
    #                    f'{self.client.account.address}')
    #
    #     bgt_contract = await self.client.contracts.get(contract_address=Contracts.BGT)
    #
    #     bgt_balance = await self.client.wallet.balance(token=Contracts.BGT)
    #
    #     if bgt_balance.Wei <= 0:
    #         logger.error(f'No available BGT for delegation | {self.client.account.address}')
    #         return
    #
    #     list_of_validators = await self.get_validators()
    #
    #     old_amount = float(bgt_balance.Ether)
    #
    #     for elem in list_of_validators:
    #         old_amount -= (float(elem['amountQueued']) + float(elem['amountDeposited']))
    #
    #     if old_amount <= 0:
    #         logger.error(f'No available BGT for delegation | {self.client.account.address}')
    #         return
    #
    #     random_validator = random.choice(self.validators)
    #     amount = TokenAmount(amount=(old_amount * 0.995))
    #     params = TxArgs(
    #         validator=random_validator['address'],
    #         amount=int(amount.Wei)
    #     )
    #
    #     tx_params = TxParams(
    #         to=bgt_contract.address,
    #         data=bgt_contract.encodeABI('queueBoost', args=params.tuple())
    #     )
    #
    #     tx = await self.client.transactions.sign_and_send(tx_params=tx_params)
    #
    #     receipt = await tx.wait_for_receipt(client=self.client, timeout=300)
    #     if receipt:
    #         logger.success(f'Delegated {amount.Ether} BGT | Validator: {random_validator["name"]} | '
    #                        f'{tx.hash.hex()} | {self.client.account.address}')
    #     else:
    #         logger.error(f'{failed_text}! | {self.client.account.address}')
    #
    # async def confirm_delegation(self) -> None:
    #     """
    #         Confirms BGT delegations for validators.
    #
    #         This function performs the following steps:
    #         1. Retrieves the user's BGT balance.
    #         2. If no BGT is available for activation, logs an error and exits.
    #         3. Fetches the current block number.
    #         4. Retrieves a list of validators and filters them based on their queued amounts.
    #         5. For each validator with queued amounts older than a current block,
    #         adds their address to the confirmation list.
    #         6. Sends a transaction to confirm the delegation for each validator in the confirmation list.
    #         7. Logs the success or failure of each confirmation.
    #
    #         Notes:
    #         - The function selects validators with queued amounts that have been pending for more than 8300 blocks.
    #         - The transaction is sent with a nonce to avoid conflicts.
    #     """
    #     logger.info(f'Starting delegation confirmation | {self.client.account.address}')
    #
    #     failed_text = (f'Failed to confirm BGT delegation | '
    #                    f'{self.client.account.address}')
    #
    #     bartio_station = await self.client.contracts.get(contract_address=Contracts.BGT)
    #
    #     station_balance = await bartio_station.functions.balanceOf(self.client.account.address).call()
    #
    #     if station_balance <= 0:
    #         logger.error(f'No active delegations for claiming BGT | {self.client.account.address}')
    #         return
    #
    #     current_block = await self.client.w3.eth.block_number
    #     list_of_validators = await self.get_validators()
    #     confirm_list = []
    #
    #     for elem in list_of_validators:
    #         if float(elem['amountQueued']) > 0:
    #             if int(elem['latestBlock']) + 8300 <= int(current_block):
    #                 confirm_list.append(elem['coinbase'])
    #             else:
    #                 continue
    #         else:
    #             continue
    #
    #     if len(confirm_list) == 0:
    #         logger.warning(f'Nothing to confirm yet | {self.client.account.address}')
    #         return
    #
    #     nonce = await self.client.wallet.nonce()
    #     for address in confirm_list:
    #         params = TxArgs(
    #             address=self.client.w3.to_checksum_address(address)
    #         )
    #
    #         tx_params = TxParams(
    #             to=bartio_station.address,
    #             data=bartio_station.encodeABI('activateBoost', args=params.tuple()),
    #             nonce=nonce
    #         )
    #         tx = await self.client.transactions.sign_and_send(tx_params=tx_params)
    #
    #         receipt = await tx.wait_for_receipt(client=self.client, timeout=300)
    #         if receipt:
    #             logger.success(f'Confirmed BGT delegation | Validator: '
    #                            f'{self.client.w3.to_checksum_address(address)} | '
    #                            f'{tx.hash.hex()} | {self.client.account.address}')
    #         else:
    #             logger.error(f'{failed_text}! | {self.client.account.address}')
    #         nonce += 1
    #     return
    #
    # async def get_validators(self) -> list[dict]:
    #     """
    #         Retrieves the list of validators and their delegation information.
    #
    #         This function performs the following steps:
    #         1. Sends a GraphQL query to the API to fetch user-specific validator data.
    #         2. Returns a list of dictionaries containing the validator information such as:
    #             - `amountQueued`: The amount of BGT queued for delegation.
    #             - `amountDeposited`: The amount of BGT already deposited.
    #             - `latestBlock`: The latest block number.
    #             - `coinbase`: The address of the validator's coinbase.
    #         3. If the API request is successful (status code <= 201), it returns the list of validators.
    #         4. If the request fails, it logs an error and raises an exception.
    #     """
    #     async with httpx.AsyncClient(proxy=self.client.proxy) as client:
    #         headers = {
    #             'accept': '*/*',
    #             'accept-language': 'ru,en-US;q=0.9,en;q=0.8,ja;q=0.7,kk;q=0.6,fr;q=0.5',
    #             'content-type': 'application/json',
    #             'dnt': '1',
    #             'origin': 'https://bartio.station.berachain.com',
    #             'priority': 'u=1, i',
    #             'referer': 'https://bartio.station.berachain.com/',
    #             'sec-ch-ua': '"Not A(Brand";v="8", "Chromium";v="132", "Google Chrome";v="132"',
    #             'sec-ch-ua-mobile': '?0',
    #             'sec-ch-ua-platform': '"Windows"',
    #             'sec-fetch-dest': 'empty',
    #             'sec-fetch-mode': 'cors',
    #             'sec-fetch-site': 'cross-site',
    #             'user-agent': self.random_useragent,
    #         }
    #
    #         json_data = {
    #             'operationName': 'GetUserValidatorInformation',
    #             'variables': {
    #                 'address': f'{self.client.account.address}',
    #             },
    #             'query': 'query GetUserValidatorInformation($address: String!) '
    #                      '{\n  userValidatorInformations(where: {user: $address}, first: 1000) '
    #                      '{\n    id\n    amountQueued\n    amountDeposited\n    latestBlock\n    '
    #                      'user\n    coinbase\n    __typename\n  }\n}',
    #         }
    #
    #         response = await client.post(
    #             'https://api.goldsky.com/api/public/project_clq1h5ct0g4a201x18tfte5iv/subgraphs/'
    #             'bgt-staker-subgraph/v1/gn',
    #             headers=headers,
    #             json=json_data,
    #         )
    #         if response.status_code <= 201:
    #             data = response.json()
    #             return data['data']['userValidatorInformations']
    #         logger.error('Error when requesting active delegations')
    #         raise Exception
    #
    # async def get_bera_balance(self) -> None:
    #     """
    #         Retrieves the balance of the account associated with the client and logs it.
    #
    #         This function fetches the balance of the account, logs it with a precision of 4 decimal places,
    #         and returns the balance in Ether.
    #     """
    #     try:
    #         balance = await self.client.wallet.balance()
    #         logger.info(f'Balance {self.client.account.address} | {round(balance.Ether, 4)}')
    #     except Exception as e:
    #         logger.error(f'Failed to get balance | {self.client.account.address}: {str(e)}')
