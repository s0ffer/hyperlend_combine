import time
from fake_useragent import UserAgent
from loguru import logger

from eth_async.client import Client
from eth_async.data.models import TokenAmount
from eth_async.utils.web_requests_old import async_get


class Base:
    def __init__(self, client: Client, api_key: str, proxy_info: dict):
        self.client = client
        self.api_key = api_key,
        self.proxy_info = proxy_info
        self.random_useragent = UserAgent().chrome

    async def get_amount_out(self, amount: TokenAmount, to_ibgt: bool = True) -> TokenAmount:
        """
            Requests the token amount output (either iBGT or the reverse) from the API.

            Args:
                amount (TokenAmount): The input token amount (in Wei).
                to_ibgt (bool): If True, convert to iBGT, else the reverse conversion.

            Returns:
                TokenAmount: The resulting token amount after conversion.

            Raises:
                Exception: If the API fails after retrying the maximum number of attempts.
        """
        logger.info(f'Requesting to get iBGT amount | {self.client.account.address}')

        if to_ibgt:
            tokenIn = '0x7507c1dc16935B82698e4C63f2746A2fCf994dF8'
            tokenOut = '0x46eFC86F0D7455F135CC9df501673739d513E982'
        else:
            tokenIn = '0x46eFC86F0D7455F135CC9df501673739d513E982'
            tokenOut = '0x7507c1dc16935B82698e4C63f2746A2fCf994dF8'

        headers = {
            'accept': '*/*',
            'accept-language': 'ru,en-US;q=0.9,en;q=0.8,ja;q=0.7,kk;q=0.6,fr;q=0.5',
            'origin': 'https://app.kodiak.finance',
            'priority': 'u=1, i',
            'referer': 'https://app.kodiak.finance/',
            'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'cross-site',
            'user-agent': self.random_useragent,
        }

        params = {
            'protocols': 'v3,mixed',
            'tokenInAddress': tokenIn,
            'tokenInChainId': '80084',
            'tokenOutAddress': tokenOut,
            'tokenOutChainId': '80084',
            'amount': str(amount.Wei),
            'type': 'exactIn',
        }

        attempt = 0
        max_attempts = 5

        while attempt < max_attempts:
            try:
                response = await async_get(url='https://ebey72gfe6.execute-api.us-east-1.amazonaws.com/prod/quote',
                                           headers=headers,
                                           params=params,
                                           proxy=self.client.proxy)
                ibgt_amount = response['route'][0][0]['amountOut']
                return TokenAmount(amount=ibgt_amount, decimals=18, wei=True)
            except KeyError as e:
                attempt += 1
                logger.warning(f"Attempt {attempt}/{max_attempts} failed. Error: {e} | {self.client.account.address}")
                if attempt < max_attempts:
                    logger.warning('Next attempt')
                    time.sleep(3)
                else:
                    logger.warning('Attempts are over')

    async def approve_interface(self, token_address, spender, amount: TokenAmount | None = None,
                                station_max: bool | None = False) -> bool:
        """
           Approves a spender to spend a certain amount of a token on behalf of the account.

           Args:
               token_address (str): The address of the token to approve.
               spender (str): The address of the spender (contract or wallet).
               amount (TokenAmount | None): The amount to approve. If None, the entire balance will be approved.
               station_max (bool | None): Whether to approve the maximum amount at the station. Default is False.

           Returns:
               bool: True if approval was successful, False otherwise.
       """
        balance = await self.client.wallet.balance(token=token_address)
        if balance.Wei <= 0:
            logger.warning(f'No balance available for token {token_address} | {self.client.account.address}')
            return False

        # If no amount is specified or the amount exceeds the balance, use the full balance
        amount = amount or balance
        if amount.Wei > balance.Wei:
            logger.warning(f'Amount exceeds balance for token {token_address} | {self.client.account.address}')
            return False

        # Check if approval is already sufficient
        approved = await self.client.transactions.approved_amount(
            token=token_address,
            spender=spender,
            owner=self.client.account.address
        )

        if amount.Wei <= approved.Wei:
            logger.info(f'Approval already sufficient for spender {spender} | {self.client.account.address}')
            return True

        # Approve the token transfer
        try:
            tx = await self.client.transactions.approve(
                token=token_address,
                spender=spender,
                amount=amount,
                station_max=station_max
            )

            # Wait for receipt to confirm transaction
            receipt = await tx.wait_for_receipt(client=self.client, timeout=300)
            if receipt:
                logger.info(f'Approval successful for spender {spender} | {self.client.account.address}')
                return True
            else:
                logger.error(f'Approval transaction failed for spender {spender} | {self.client.account.address}')
                return False
        except Exception as e:
            logger.error(f'Error during approval for spender {spender} | {self.client.account.address}: {e}')
            return False
