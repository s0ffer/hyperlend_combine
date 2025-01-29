import asyncio
from typing import Literal

from web3.exceptions import ContractLogicError
from web3.types import TxParams
from capmonstercloudclient import CapMonsterClient, ClientOptions
from capmonstercloudclient.requests import TurnstileRequest
import httpx

from data.models import Contracts
from eth_async.data.models import TokenAmount
from tasks.base import Base
from utils import logger


class Hyperlend(Base):
    token_data = {
        'BTC': {
            'data': '0x617ba037000000000000000000000000453b63484b11bbf0b61fc7e854f8dac7bde7d458',
            'pool': '0x1e85CCDf0D098a9f55b82F3E35013Eda235C8BD8'
        },
        'ETH': {
            'data': '0x474cf53d000000000000000000000000e0bdd7e8b7bf5b15dcda6103fcbba82a460ae2c7',
            'pool': '0xd2b21707d7a574D6A744FB600826770F9FBA6f80'
        },
        'HYPE': {
            'data': '0x474cf53d00000000000000000000000068cd2d3503cb4a334522e557c5ba1a0d5fe56bfc',
            'pool': '0x272C635e84fC122239933bE56089C99653FCd255'
        },
    }

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
        current_balance = await self.client.wallet.balance()

        if current_balance.Wei > 0:
            logger.warning(f'Already claimed, once per wallet! | {self.client.account.address} | '
                           f'{round((await self.client.wallet.balance()).Ether, 6)} HYPE')
            return

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

            max_attempts = 2
            attempt = 0
            while attempt <= max_attempts:
                try:
                    response = await client.post('https://api.hyperlend.finance/ethFaucet',
                                                 headers=headers,
                                                 json=json_data)
                    break
                except Exception as e:
                    logger.warning(f'Failed request, {attempt}/{max_attempts} attempt | {self.client.account.address}')
                    attempt += 1
                    if attempt == max_attempts:
                        logger.error(f'Failed request: {e} | {self.client.account.address}')
                        return
                    await asyncio.sleep(5)

        result = response.json()
        msg = result.get("response", "")
        if isinstance(msg, dict) and msg.get('status') == 1:
            logger.success(f'Claimed native tokens | {self.client.account.address} | '
                           f'{round((await self.client.wallet.balance()).Ether, 6)} HYPE')
        elif 'user_already_claimed' in msg:
            logger.warning(f'Already claimed, once per wallet! | {self.client.account.address} | '
                           f'{round((await self.client.wallet.balance()).Ether, 6)} HYPE')
        else:
            logger.error(f'{msg} | {self.client.account.address} | '
                         f'{round((await self.client.wallet.balance()).Ether, 6)} HYPE')

    async def claim_mbtc_faucet(self) -> None:
        logger.info(f'Starting MBTC faucet claim | {self.client.account.address}')

        failed_text = f'Failed to claim MBTC faucet'

        tx_params = TxParams(
            to=Contracts.HYPERLEND_FAUCET.address,
            data='0x4e71d92d'  # Claim()
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

    async def supply_mbtc(self, amount: TokenAmount):
        await self._supply(amount=amount, token_name='BTC')
        return

    async def supply_eth(self, amount: TokenAmount):
        await self._supply(amount=amount, token_name='ETH')
        return

    async def supply_hype(self, amount: TokenAmount):
        await self._supply(amount=amount, token_name='HYPE')
        return

    async def _supply(self, amount: TokenAmount, token_name: Literal['BTC', 'ETH', 'HYPE']) -> None:
        logger.info(f'Starting supply of {token_name} | {self.client.account.address}')

        failed_text = f'Failed to supply {token_name} on Hyperlend | {self.client.account.address}'

        native_balance = await self.client.wallet.balance()

        if native_balance.Wei <= 0:
            logger.error(f'Insufficient native balance for supply | {self.client.account.address}')
            return

        if token_name == 'BTC':
            btc_balance = await self.client.wallet.balance(token='0x453b63484b11bbF0b61fC7E854f8DAC7bdE7d458')

            if btc_balance.Wei < amount.Wei:
                logger.error(f'Insufficient MBTC balance for supply | {self.client.account.address}')
                return

            if await self.approve_interface(
                    token_address=f'0x{self.token_data.get('BTC', '').get('data', '')[-40:]}',
                    spender=self.token_data.get('BTC', '').get('pool', ''),
                    station_max=True
            ):
                logger.info(f'Approved MBTC for pool | {self.client.account.address}')
            else:
                logger.error(f'Failed to approve MBTC | {self.client.account.address}')
                return

            data = (f'{self.token_data.get('BTC', '').get('data', '')}'
                    f'{amount.Wei:064x}'
                    f'{int(self.client.account.address, 16):064x}'
                    f'{0:064x}')
            pool = self.token_data.get('BTC', {}).get('pool', '')
            value = 0

        if token_name == 'ETH' or token_name == 'HYPE':
            if native_balance.Wei < amount.Wei:
                logger.error(f'Insufficient {token_name} balance for supply | {self.client.account.address}')
                return

            data = (f'{self.token_data.get(token_name, '').get('data', '')}'
                    f'{int(self.client.account.address, 16):064x}'
                    f'{0:064x}')
            pool = self.token_data.get(token_name, {}).get('pool', '')
            value = amount.Wei

        tx_params = TxParams(
            to=pool,
            data=data,
            value=value
        )

        tx = await self.client.transactions.sign_and_send(tx_params=tx_params)

        if tx is None:
            return
        else:
            receipt = await tx.wait_for_receipt(client=self.client, timeout=300)
            if receipt:
                logger.success(
                    f'Supplied {amount.Ether} {token_name} on Hyperlend: {tx.hash.hex()} '
                    f'| {self.client.account.address}')
                return
            logger.error(f'{failed_text}! | {self.client.account.address}')

    # async def get_balances(self) -> None:
    #       """
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
