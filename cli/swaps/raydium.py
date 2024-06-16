from swaps import solutils
from solana.rpc.api import Client
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from spl.token.client import Token
from spl.token.core import _TokenCore
from solders.compute_budget import set_compute_unit_price
from solana.rpc.commitment import Commitment
from spl.token.instructions import close_account, CloseAccountParams
from solana.rpc.types import TokenAccountOpts
import solana
from solana.transaction import Transaction
from solders.signature import Signature
from typing import Union
import json
import time

lamps = 1000000000
with open('config.json', 'r') as file:
    data = json.load(file)

COMPUTE_UNITS = data.get('Raydium Fee', 0.00025)  # Default value if not set in config.json
SLIPPAGE = data.get('Raydium Slippage', 1.9)  # Default value if not set in config.json


def calculate_percentage_increase(buy, current):
    increase = current - buy
    percentage_increase = (increase / buy) * 100
    return percentage_increase


class RaySwap:
    def __init__(self, client: Client, coin_address: str, amount_sol: float, keypair: Keypair):
        self.client = client
        self.coin_address = coin_address
        self.amount_sol = amount_sol
        self.keypair = keypair
        self.purchase_price = 0.0

    def buy(self) -> Union[bool, Signature]:
        mint = Pubkey.from_string(self.coin_address)
        # pool_keys = solutils.fetch_pool_keys(str(mint))
        pool_keys = solutils.fetch_pool_keys_personal(str(mint))
        amount_in = int(self.amount_sol * lamps)
        account_program_id = self.client.get_account_info_json_parsed(mint)
        token_program_id = account_program_id.value.owner
        sat_address, sta_instructions = solutils.get_token_account(self.client, self.keypair.pubkey(), mint)
        balance_needed = Token.get_min_balance_rent_for_exempt_for_account(self.client)
        wrapped_sol_token_account, swap_tx, payer, wrapped_sol_account_keypair, opts, = _TokenCore._create_wrapped_native_account_args(
            token_program_id, self.keypair.pubkey(), self.keypair, amount_in,
            False, balance_needed, Commitment("confirmed"))
        # swap_tx.add(set_compute_unit_price(int(0.00025 * 10 ** 9)))
        swap_tx.add(set_compute_unit_price(int(COMPUTE_UNITS * 10 ** 9)))
        shitcoin_price, decimal_shifter = solutils.get_shitcoin_price(self.client, self.coin_address)
        amount_we_want_to_buy = (self.amount_sol / shitcoin_price) * 0.95  # 5% slippage
        instructions_swap = solutils.make_swap_instruction(amount_in,
                                                           wrapped_sol_token_account,
                                                           sat_address,
                                                           pool_keys,
                                                           mint,
                                                           self.client,
                                                           payer,
                                                           amount_we_want_to_buy,
                                                           decimal_shifter=decimal_shifter
                                                           )
        params = CloseAccountParams(account=wrapped_sol_token_account, dest=payer.pubkey(), owner=payer.pubkey(),
                                    program_id=token_program_id)
        close_acc = (close_account(params))
        if sta_instructions:
            swap_tx.add(sta_instructions)
        swap_tx.add(instructions_swap)
        swap_tx.add(close_acc)
        try:
            try:
                txn = self.client.send_transaction(swap_tx, payer, wrapped_sol_account_keypair)
            except Exception as e:
                #print('also bad', e)
                return False
            self.purchase_price = shitcoin_price
            return txn.value
        except solana.rpc.core.RPCException:
            #print('bad')
            return False

    def sell(self, half: bool = False, previous_balance: float = float('inf')) -> bool:
        # if half is true, continue selling half until remaining bal is less than before
        # else keep going until 0
        mint = Pubkey.from_string(self.coin_address)
        sol = Pubkey.from_string("So11111111111111111111111111111111111111112")
        account_program_id = self.client.get_account_info_json_parsed(mint)
        token_program_id = account_program_id.value.owner
        # pool_keys = solutils.fetch_pool_keys(str(mint))
        pool_keys = solutils.fetch_pool_keys_personal(str(mint))
        while True:
            amount_in = 0
            try:
                accounts = self.client.get_token_accounts_by_owner_json_parsed(self.keypair.pubkey(), TokenAccountOpts(
                    program_id=token_program_id)).value
            except:
                continue
            for account in accounts:
                mint_in_acc = account.account.data.parsed['info']['mint']
                if mint_in_acc == str(mint):
                    amount_in = int(account.account.data.parsed['info']['tokenAmount']['amount'])  # our token balance
                    if amount_in == 0:
                        print('no bal, sold already')
                        return True
                    if half and amount_in < previous_balance:
                        return True
                    amount_in = amount_in / 2 if half else amount_in
            swap_token_account = solutils.sell_get_token_account(self.client, self.keypair.pubkey(), mint)
            wst_account, wst_account_instructions = solutils.get_token_account(self.client, self.keypair.pubkey(), sol)
            if not swap_token_account:
                continue
            shitcoin_price, decimal_shifter = solutils.get_shitcoin_price(self.client, self.coin_address)
            instructions_swap = solutils.make_swap_instruction(amount_in,
                                                               swap_token_account,
                                                               wst_account,
                                                               pool_keys,
                                                               mint,
                                                               self.client,
                                                               self.keypair,
                                                               0,
                                                               selling=True,
                                                               maximum_sol_we_spend=shitcoin_price * amount_in
                                                               )
            params = CloseAccountParams(account=wst_account, dest=self.keypair.pubkey(), owner=self.keypair.pubkey(),
                                        program_id=token_program_id)
            close_acc = (close_account(params))
            swap_tx = Transaction()
            signers = [self.keypair]
            if wst_account_instructions:
                swap_tx.add(wst_account_instructions)
            swap_tx.add(instructions_swap)
            swap_tx.add(close_acc)
            swap_tx.add(set_compute_unit_price(int(0.0004 * 10 ** 9)))
            try:
                txn = self.client.send_transaction(swap_tx, *signers, selling=True)
                tx_id_string_sig = txn.value
                string_of_tx = json.loads(txn.to_json())['result']
                try:
                    status = self.client.get_transaction(tx_id_string_sig, "json")
                    if not status.value.transaction.meta.err:
                        # print('dub')
                        continue
                except Exception as e:
                    if 'NoneType' not in str(e):
                        # print('very likely success')
                        time.sleep(15)
                        continue
                    # print('possible success')
                    time.sleep(15)
                    continue
            except Exception as e:
                # print('failed simulation')
                continue

    def check_if_price_profit(self, prints=0) -> Union[bool, int]:
        # check coin_address price, if its 2x buy price return 2, 10x return 10, < 2x return False
        shitcoin_price, decimal_shifter = solutils.get_shitcoin_price(self.client, self.coin_address)
        if prints % 10 == 0:
            print('profit %', self.coin_address[:4], calculate_percentage_increase(self.purchase_price, shitcoin_price))
        if shitcoin_price >= self.purchase_price * 10:
            return 10
        if shitcoin_price >= self.purchase_price * 2:
            return 2
        return False

    def check_balance(self) -> float:
        mint = Pubkey.from_string(self.coin_address)
        account_program_id = self.client.get_account_info_json_parsed(mint)
        token_program_id = account_program_id.value.owner
        while True:
            try:
                accounts = self.client.get_token_accounts_by_owner_json_parsed(self.keypair.pubkey(), TokenAccountOpts(
                    program_id=token_program_id)).value
            except:
                continue
            for account in accounts:
                mint_in_acc = account.account.data.parsed['info']['mint']
                if mint_in_acc == str(mint):
                    amount_in = int(account.account.data.parsed['info']['tokenAmount']['amount'])  # our token balance
                    if amount_in > 0:
                        return amount_in
            return 0.0

    def check_price(self):
        shitcoin_price, decimal_shifter = solutils.get_shitcoin_price(self.client, self.coin_address)
        return shitcoin_price, decimal_shifter
