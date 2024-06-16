import requests
from solana.rpc.types import TokenAccountOpts
from spl.token.instructions import create_associated_token_account, get_associated_token_address
from solders.instruction import Instruction
from datetime import datetime, timedelta
from swaps import layout
import json
from solana.transaction import AccountMeta
import time
from datetime import datetime
from solders.pubkey import Pubkey
from solana.rpc.api import Client
import base64
import construct as cs
import base58
from construct import Struct, Bytes, Int64ul
from solana.rpc import types
from solana.rpc.commitment import Commitment
from solana.rpc.types import MemcmpOpts, DataSliceOpts

SERUM_PROGRAM_ID = Pubkey.from_string('srmqPvymJeFKQ4zGQed1GFppgkRHL9kaELCbyksJtPX')
AMM_PROGRAM_ID = Pubkey.from_string('675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8')
lil_cache = {}
mc = {}
with open('config.json', 'r') as file:
    data = json.load(file)
COMPUTE_UNITS = data.get('Raydium Fee')
SLIPPAGE = data.get('Raydium Slippage')


def parse_liquidity_state_layout_v4(data):
    struct_format = cs.Struct(
        "status" / cs.Int64ul,
        "nonce" / cs.Int64ul,
        "maxOrder" / cs.Int64ul,
        "depth" / cs.Int64ul,
        "baseDecimal" / cs.Int64ul,
        "quoteDecimal" / cs.Int64ul,
        "state" / cs.Int64ul,
        "resetFlag" / cs.Int64ul,
        "minSize" / cs.Int64ul,
        "volMaxCutRatio" / cs.Int64ul,
        "amountWaveRatio" / cs.Int64ul,
        "baseLotSize" / cs.Int64ul,
        "quoteLotSize" / cs.Int64ul,
        "minPriceMultiplier" / cs.Int64ul,
        "maxPriceMultiplier" / cs.Int64ul,
        "systemDecimalValue" / cs.Int64ul,
        "minSeparateNumerator" / cs.Int64ul,
        "minSeparateDenominator" / cs.Int64ul,
        "tradeFeeNumerator" / cs.Int64ul,
        "tradeFeeDenominator" / cs.Int64ul,
        "pnlNumerator" / cs.Int64ul,
        "pnlDenominator" / cs.Int64ul,
        "swapFeeNumerator" / cs.Int64ul,
        "swapFeeDenominator" / cs.Int64ul,
        "baseNeedTakePnl" / cs.Int64ul,
        "quoteNeedTakePnl" / cs.Int64ul,
        "quoteTotalPnl" / cs.Int64ul,
        "baseTotalPnl" / cs.Int64ul,
        "poolOpenTime" / cs.Int64ul,
        "punishPcAmount" / cs.Int64ul,
        "punishCoinAmount" / cs.Int64ul,
        "orderbookToInitTime" / cs.Int64ul,
        "swapBaseInAmount" / cs.Int64ul,
        "swapQuoteOutAmount" / cs.Int64ul,
        "swapBase2QuoteFee" / cs.Int64ul,
        "swapQuoteInAmount" / cs.Int64ul,
        "swapBaseOutAmount" / cs.Int64ul,
        "swapQuote2BaseFee" / cs.Int64ul,
        "baseVault" / cs.Bytes(32),
        "quoteVault" / cs.Bytes(32),
        "baseMint" / cs.Bytes(32),
        "quoteMint" / cs.Bytes(32),
        "lpMint" / cs.Bytes(32),
        "openOrders" / cs.Bytes(32),
        "marketId" / cs.Bytes(32),
        "marketProgramId" / cs.Bytes(32),
        "targetOrders" / cs.Bytes(32),
        "withdrawQueue" / cs.Bytes(32),
        "lpVault" / cs.Bytes(32),
        "owner" / cs.Bytes(32),
        "lpReserve" / cs.Int64ul,
        "padding" / cs.Array(3, cs.Int64ul)
    )
    pool = {}
    parsed_data = struct_format.parse(data)
    # Convert bytes to hexadecimal strings
    parsed_data = parsed_data.copy()
    for key, value in parsed_data.items():

        if isinstance(value, bytes):
            blob_32 = cs.Bytes(32)
            # print(key, value)
            # print(blob_32.parse(value))
            nonfucked = blob_32.parse(value)
            pool[key] = nonfucked
        else:
            pool[key] = value
    return pool


def get_associated_authority(program_id, market_id, nonce):
    # print(program_id, market_id)
    market_id = Pubkey.from_string(market_id)
    program_id = Pubkey.from_string(program_id)
    seeds = bytes(market_id)
    # nonce = 0
    # while nonce < 100:
    # print('nonce fr', nonce)
    while True:
        try:
            public_key = Pubkey.create_program_address([seeds, Int64ul.build(nonce)], program_id)
            #  print('SUCCESS', public_key)
            return public_key
            # return {"public_key": public_key, "nonce": nonce}
        except BaseException as e:
            print('WRONG NONCE', e)
            pass
        nonce += 1


def get_market_info3(market_id):
    # change this later
    endpoint = 'https://api.mainnet-beta.solana.com'
    solana_client = Client(endpoint)
    info = json.loads(solana_client.get_account_info_json_parsed(Pubkey.from_string(market_id)).to_json())
    data = info['result']['value']['data']
    data_64 = base64.b64decode(data[0])
    # print(data_64)
    r = parse_market_state_layout_v3(data_64)
    return r


def get_aid(program_id, market_id):
    ps = program_id
    ms = market_id
    program_bytes = base58.b58decode(
        ps)
    market_bytes = base58.b58decode(
        ms
    )

    json_string = "[" + ",".join(map(lambda b: str(b), program_bytes)) + "]"
    # print(json_string)
    # print(program_bytes)
    program_id = Pubkey.from_string(program_id)
    market_id = Pubkey.from_string(market_id)
    seeds = [program_bytes, market_bytes, bytes("amm_associated_seed", 'utf-8')]
    # seed = b"amm_associated_seed"
    # res = Pubkey.create_program_address(seeds, program_id)
    res = program_id.find_program_address(seeds, program_id)
    # public_key, _ = find_program_address(
    #     [program_id.to_bytes(), market_id.to_bytes(), seed],
    #     program_id
    # )
    return res


def parse_market_state_layout_v3(data):
    # Define the struct format
    # THIS IS THE STRUCTURE INSIDE OPENBOOK??
    struct_format = Struct(
        "blob_1" / Bytes(5),
        "account_flags" / Bytes(8),  # Assuming accountFlagsLayout('accountFlags') is 8 bytes
        "own_address" / Bytes(32),  # Assuming publicKey('ownAddress') is 32 bytes
        "vault_signer_nonce" / Int64ul,  # TODO this is the real nonce??
        "base_mint" / Bytes(32),  # Assuming publicKey('baseMint') is 32 bytes <<<<< This is usually 53 bytes in
        "quote_mint" / Bytes(32),  # Assuming publicKey('quoteMint') is 32 bytes <<<< when flipped its 32 more
        "base_vault" / Bytes(32),  # Assuming publicKey('baseVault') is 32 bytes
        "base_deposits_total" / Int64ul,
        "base_fees_accrued" / Int64ul,
        "quote_vault" / Bytes(32),  # Assuming publicKey('quoteVault') is 32 bytes
        "quote_deposits_total" / Int64ul,
        "quote_fees_accrued" / Int64ul,
        "quote_dust_threshold" / Int64ul,
        "request_queue" / Bytes(32),  # Assuming publicKey('requestQueue') is 32 bytes
        "event_queue" / Bytes(32),  # Assuming publicKey('eventQueue') is 32 bytes
        "bids" / Bytes(32),  # Assuming publicKey('bids') is 32 bytes
        "asks" / Bytes(32),  # Assuming publicKey('asks') is 32 bytes
        "base_lot_size" / Int64ul,
        "quote_lot_size" / Int64ul,
        "fee_rate_bps" / Int64ul,
        "referrer_rebates_accrued" / Int64ul,
        "blob_2" / Bytes(7)
    )
    pool = {}
    # Parse the data
    parsed_data = struct_format.parse(data)
    for key, value in parsed_data.items():

        if isinstance(value, bytes) and key != 'blob_1' and key != 'account_flags' and key != 'blob_2':
            blob_32 = cs.Bytes(32)
            # print(key, value)
            # print(blob_32.parse(value))
            nonfucked = blob_32.parse(value)
            pool[key] = nonfucked
        elif key == 'blob_1':
            blob_32 = cs.Bytes(5)
            nonfucked = blob_32.parse(value)
            pool[key] = nonfucked
        elif key == 'account_flags':
            blob_32 = cs.Bytes(8)
            nonfucked = blob_32.parse(value)
            pool[key] = nonfucked
        elif key == 'blob_2':
            blob_32 = cs.Bytes(7)
            nonfucked = blob_32.parse(value)
            pool[key] = nonfucked

        else:
            pool[key] = value
    return pool


test = {"id": "FRhB8L7Y9Qq41qZXYLtC2nw8An1RJfLLxRF2x9RwLLMo",
        "baseMint": "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr",
        "quoteMint": "So11111111111111111111111111111111111111112",
        "lpMint": "mUVPGfAcfQH3RA8EucVvrisxxyRu6WomPbPZdZUnrd9", "baseDecimals": 9, "quoteDecimals": 9, "lpDecimals": 9,
        "version": 4, "programId": "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
        "authority": "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1",
        "openOrders": "4ShRqC2n3PURN7EiqmB8X4WLR81pQPvGLTPjL9X8SNQp",
        "targetOrders": "9Rz3uVwambJRhCJoJH2qBPGgkr1CWUfWfQymsax1ZMKN",
        "baseVault": "4Vc6N76UBu26c3jJDKBAbvSD7zPLuQWStBk7QgVEoeoS",
        "quoteVault": "n6CwMY77wdEftf2VF6uPvbusYoraYUci3nYBPqH1DJ5",
        "withdrawQueue": "11111111111111111111111111111111", "lpVault": "11111111111111111111111111111111",
        "marketVersion": 4, "marketProgramId": "srmqPvymJeFKQ4zGQed1GFppgkRHL9kaELCbyksJtPX",
        "marketId": "92R9ZDC7buk2gQ8kHVynnSAxKjHYGUippr9QUdZ759iF",
        "marketAuthority": "8Ym59BRuBt44GnhkQyYQPssGfY3kX4kFaHSs33PwMXbB",
        "marketBaseVault": "EBvGGuPyK4oxKpax2MNASQsRWfGoVJh4t1JJw8fuVcy3",
        "marketQuoteVault": "DRJdNZ8b8CHrq3xwTSofbhmbXFneZTQrPTgFGddJ6cDf",
        "marketBids": "Cg5SE2g3WRvXN2RfGoy1DwZxqeS96EVWT7L2aCisJv44",
        "marketAsks": "5txxTo3cBYytAo97Ca9hCT3zJCxv9knHXqNP9W2xEJkN",
        "marketEventQueue": "HJUAR8MELHWJTsz72mbEpxcre83YBx61h2hsqKgvG59R",
        "lookupTableAccount": "2LNsFM7KjT3PC4ZFQBu4DMZk2n5FewoJM5bPzMnSp5wP"}


def get_liquid4(pool_address):
    endpoint = 'https://api.mainnet-beta.solana.com'
    solana_client = Client(endpoint)
    pool = Pubkey.from_string(pool_address)
    info = json.loads(solana_client.get_account_info_json_parsed(pool).to_json())
    # print(info, pool)
    data = info['result']['value']['data']
    data_64 = base64.b64decode(data[0])
    token_account_data = parse_liquidity_state_layout_v4(data_64)
    CORRECT_BASE = Pubkey.from_bytes(token_account_data.get('quoteVault'))
    CORRECT_QUOTE = Pubkey.from_bytes(token_account_data.get('baseMint'))
    return token_account_data, token_account_data.get('nonce')


def get_liquid_ray(pool_address):
    endpoint = 'https://api.mainnet-beta.solana.com'
    solana_client = Client(endpoint)
    pool = Pubkey.from_string(pool_address)
    info = json.loads(solana_client.get_account_info_json_parsed(pool).to_json())
    print('acc inf', info)
    return


def get_al(program_id: str):
    # THIS IS FOR ind 1 AUTHORITY
    program_id = Pubkey.from_string(program_id)
    seeds = [
        bytes([97, 109, 109, 32, 97, 117, 116, 104, 111, 114, 105, 116, 121])
    ]
    result = program_id.find_program_address(seeds, program_id)
    print(result)


def get_atc(coin_add):
    rpc = "https://raydium-raydium-5ad5.mainnet.rpcpool.com/"
    rpc_headers = {'authority': 'raydium-raydium-5ad5.mainnet.rpcpool.com', 'accept': '*/*',
                   'accept-language': 'en-US,en;q=0.9', 'cache-control': 'no-cache',
                   'content-type': 'application/json', 'dnt': '1', 'origin': 'https://raydium.io',
                   'pragma': 'no-cache', 'referer': 'https://raydium.io/',
                   'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                   'sec-ch-ua-mobile': '?0', 'sec-ch-ua-platform': '"Windows"', 'sec-fetch-dest': 'empty',
                   'sec-fetch-mode': 'cors', 'sec-fetch-site': 'cross-site',
                   'solana-client': 'js/0.0.0-development',
                   'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, '
                                 'like Gecko) Chrome/120.0.0.0 Safari/537.36', }
    client = Client(rpc, extra_headers=rpc_headers)
    coin_add = Pubkey.from_string(coin_add)
    opts = types.TokenAccountOpts(program_id=coin_add)
    res = client.get_token_accounts_by_owner_json_parsed(coin_add, opts)
    print(res.to_json())


def locally_match_pools(mint):
    with open(r'pooldump.json', 'r') as file:
        j_file = json.load(file)
        for i in j_file:
            if i[4] == mint:
                return i


upack_cache = {}

"""
def get_pool(token_mint: str):

    client = Client(RAYDIUM_RPC_URL, extra_headers=RAYDIUM_HEADERS)
    market_id = client.get_program_accounts(Pubkey.from_string("srmqPvymJeFKQ4zGQed1GFppgkRHL9kaELCbyksJtPX"), filters=[388, MemcmpOpts(53, token_mint)], data_slice=DataSliceOpts(offset=53, length=64))
    market_id = market_id.value[0].pubkey

    pool_id = get_amm_id(market_id)

    raw_pool_data, raw_market_data = client.get_multiple_accounts([pool_id, market_id]).value
    market_data = raw_market_data.data
    pool_data = raw_pool_data.data

    market_info = MARKET_STATE_LAYOUT_V3.parse(market_data)
    pool_open_time = AMM_INFO_LAYOUT_V4.parse(pool_data)['poolOpenTime']

    base_vault = get_base_vault(market_id)
    quote_vault = get_quote_vault(market_id)
    open_order = get_open_order(market_id)
    target_order = get_target_order(market_id)

    amm_keys = dict()
    amm_keys["vault_nonce"] = market_info.vaultSignerNonce
    amm_keys["marketBaseVault"] = str(Pubkey.from_bytes(market_info.baseVault))
    amm_keys["marketQuoteVault"] = str(Pubkey.from_bytes(market_info.quoteVault))
    amm_keys["marketBids"] = str(Pubkey.from_bytes(market_info.bids))
    amm_keys["marketAsks"] = str(Pubkey.from_bytes(market_info.asks))
    amm_keys["marketEventQueue"] = str(Pubkey.from_bytes(market_info.eventQueue))
    amm_keys["pool_open_time"] = pool_open_time
    amm_keys["id"] = str(pool_id)
    amm_keys["marketId"] = str(market_id)
    amm_keys["baseVault"] = str(base_vault)
    amm_keys["quoteVault"] = str(quote_vault)
    amm_keys["openOrders"] = str(open_order)
    amm_keys["targetOrders"] = str(target_order)
    amm_keys["marketAuthority"] = str(get_market_authority(str(market_id), amm_keys['vault_nonce']))
    del amm_keys['vault_nonce']

    return amm_keys

"""
def fetch_pool_keys_personal(mint: str, get_all_pools=False):
    # Match up the mint with the info we got in the pools on chain monitor
    # pool = locally_match_pools(mint)
    # if not pool:
    #     print('no pool using legacy method')
    #     return fetch_pool_keys(mint)
    ray_programid = '675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8'
    ser_programid = 'srmqPvymJeFKQ4zGQed1GFppgkRHL9kaELCbyksJtPX'
    try:
        market_id = get_market_id_from_mint('srmqPvymJeFKQ4zGQed1GFppgkRHL9kaELCbyksJtPX', mint)
    except:
        # market_id = get_market_id_from_mint('9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin', mint)
        print('uh oh')
        return
    minfo3 = get_market_info3(market_id)
    nonce_2 = minfo3.get('vault_signer_nonce')
    if mint in upack_cache:
        parmin = upack_cache[mint]
    else:
        parmin = {}
        for i in minfo3.items():
            try:
                if i[0] in ['own_address', 'base_vault', 'quote_vault', 'event_queue', 'bids', 'asks']:
                    parmin[i[0]] = Pubkey.from_bytes(i[1])
            except:
                pass
        upack_cache[mint] = parmin
    idid = get_aid('675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8', market_id)
    liquid4, nonce = get_liquid4(str(idid[0]))
    # liq4, nonce = get_liquid4(str(idid))
    parliq = {}
    for i in liquid4.items():
        try:
            parliq[i[0]] = Pubkey.from_bytes(i[1])
        except:
            pass
    # token = pool[0]
    # market_id = pool[11]
    # market_program_id = pool[10]
    # liquid4, nonce = get_liquid4(str(idid))
    # market3 = get_market_info3(market_id)
    if mint in mc:
        market_authority = mc[mint]
    else:
        # market_authority = get_associated_authority(ser_programid, market_id)
        # market_authority = get_associated_authority(ser_programid, market_id, nonce)
        market_authority = get_associated_authority(ser_programid, market_id, nonce_2)
        mc[mint] = market_authority
    # print('market auth', market_authority)
    construct = {
        'amm_id': Pubkey.from_string(str(idid[0])),
        'authority': Pubkey.from_string('5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1'),
        'base_mint': parliq['quoteMint'],
        'base_decimals': liquid4['baseDecimal'],
        'quote_mint': parliq['lpMint'],
        'quote_decimals': liquid4['quoteDecimal'],
        'lp_mint': parliq['openOrders'],
        'open_orders': parliq['marketId'],
        'target_orders': parliq['withdrawQueue'],
        'base_vault': parliq['quoteVault'],
        'quote_vault': parliq['baseMint'],
        'market_id': parmin['own_address'],
        'market_base_vault': parmin['base_vault'],
        'market_quote_vault': parmin['quote_vault'],
        'market_authority': market_authority,
        'bids': parmin['bids'],
        'asks': parmin['asks'],
        'event_queue': parmin['event_queue']
    }
    return construct


def extract_pool_info(pools_list: list, mint: str):
    for pool in pools_list:
        if pool['baseMint'] == mint and pool['quoteMint'] == 'So11111111111111111111111111111111111111112':
            return pool
        elif pool['quoteMint'] == mint and pool['baseMint'] == 'So11111111111111111111111111111111111111112':
            return pool
    return {}


def get_pool_from_local(date='all'):
    try:
        with open(f'pool_caches/{date}_pool.json', 'r') as file:
            file_json = json.load(file)
        return file_json
    except FileNotFoundError:
        return False


def dump_pool_to_json(pool_json, date='all'):
    with open(f'pool_caches/{date}_pool.json', 'w') as outfile:
        json.dump(pool_json, outfile, indent=4)


def fetch_pool_keys(mint: str, get_all_pools=False):
    if mint in lil_cache:
        return lil_cache[mint]

    cookies = {
        '__cuid': 'd8e9d4efa416426fa6448d8f027ad144',
        'amp_fef1e8': 'eca5cec3-b282-4dce-93da-0f9646858a9aR...1hkd1t34u.1hkd1tc1t.7.0.7',
        '__cf_bm': 's7xrGG6ju7EkGHr.q2.SJLCkfrR3a8xSgz0llQpdnWk-1707033154-1-AdyWX5A7jwGyzrN4e/19lc4CPjnr5Atcsqbtui/lcLhN67hiEdRMQ6aP/vgMrknvpfr9p4uzgLd95/7zluYmkxw=',
    }

    headers = {
        'authority': 'api.raydium.io',
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'en-US,en;q=0.9',
        'cache-control': 'max-age=0',
        'if-modified-since': 'Sun, 04 Feb 2024 07:50:34 GMT',
        'sec-ch-ua': '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'none',
        'sec-fetch-user': '?1',
        'upgrade-insecure-requests': '1',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    }
    # random_proxy = get_proxy()
    current_datetime = datetime.now()
    future_datetime = current_datetime + timedelta(hours=6)
    formatted_date = future_datetime.strftime("%Y-%m-%d")
    while True:
        try:
            if not get_all_pools:
                resp = requests.get(
                    f'https://api.raydium.io/v2/sdk/liquidity/date/{datetime.now().strftime("%Y-%m-%d")}',
                    cookies=cookies,
                    headers=headers)

            else:
                resp = requests.get('https://api.raydium.io/v2/sdk/liquidity/mainnet.json', cookies=cookies,
                                    headers=headers)
            if resp.status_code == 304:
                if not get_all_pools:
                    pools = get_pool_from_local(date=str(formatted_date))
                else:
                    pools = get_pool_from_local()
            else:
                pools = resp.json()
                if not get_all_pools:
                    dump_pool_to_json(pools, date=str(formatted_date))
                else:
                    dump_pool_to_json(pools)
            break
        except Exception as e:
            print(e, 'problem pools')
            if not get_all_pools:
                pools = get_pool_from_local(date=str(formatted_date))
            else:
                pools = get_pool_from_local()
            if pools:
                break
            time.sleep(2)
            continue
    official = pools['official']
    unofficial = pools['unOfficial']
    all_pools = official + unofficial
    amm_info = extract_pool_info(all_pools, mint)
    if not amm_info:
        print('no pool :(')
        return fetch_pool_keys(mint, get_all_pools=True)
    lil_cache[mint] = {
        'amm_id': Pubkey.from_string(amm_info['id']),
        'authority': Pubkey.from_string(amm_info['authority']),
        'base_mint': Pubkey.from_string(amm_info['baseMint']),
        'base_decimals': amm_info['baseDecimals'],
        'quote_mint': Pubkey.from_string(amm_info['quoteMint']),
        'quote_decimals': amm_info['quoteDecimals'],
        'lp_mint': Pubkey.from_string(amm_info['lpMint']),
        'open_orders': Pubkey.from_string(amm_info['openOrders']),
        'target_orders': Pubkey.from_string(amm_info['targetOrders']),
        'base_vault': Pubkey.from_string(amm_info['baseVault']),
        'quote_vault': Pubkey.from_string(amm_info['quoteVault']),
        'market_id': Pubkey.from_string(amm_info['marketId']),
        'market_base_vault': Pubkey.from_string(amm_info['marketBaseVault']),
        'market_quote_vault': Pubkey.from_string(amm_info['marketQuoteVault']),
        'market_authority': Pubkey.from_string(amm_info['marketAuthority']),
        'bids': Pubkey.from_string(amm_info['marketBids']),
        'asks': Pubkey.from_string(amm_info['marketAsks']),
        'event_queue': Pubkey.from_string(amm_info['marketEventQueue'])
    }
    # print(lil_cache[mint])
    return {
        'amm_id': Pubkey.from_string(amm_info['id']),
        'authority': Pubkey.from_string(amm_info['authority']),
        'base_mint': Pubkey.from_string(amm_info['baseMint']),
        'base_decimals': amm_info['baseDecimals'],
        'quote_mint': Pubkey.from_string(amm_info['quoteMint']),
        'quote_decimals': amm_info['quoteDecimals'],
        'lp_mint': Pubkey.from_string(amm_info['lpMint']),
        'open_orders': Pubkey.from_string(amm_info['openOrders']),
        'target_orders': Pubkey.from_string(amm_info['targetOrders']),
        'base_vault': Pubkey.from_string(amm_info['baseVault']),
        'quote_vault': Pubkey.from_string(amm_info['quoteVault']),
        'market_id': Pubkey.from_string(amm_info['marketId']),
        'market_base_vault': Pubkey.from_string(amm_info['marketBaseVault']),
        'market_quote_vault': Pubkey.from_string(amm_info['marketQuoteVault']),
        'market_authority': Pubkey.from_string(amm_info['marketAuthority']),
        'bids': Pubkey.from_string(amm_info['marketBids']),
        'asks': Pubkey.from_string(amm_info['marketAsks']),
        'event_queue': Pubkey.from_string(amm_info['marketEventQueue'])
    }


def get_token_account(ctx, owner: Pubkey.from_string, mint: Pubkey.from_string):
    try:
        account_data = ctx.get_token_accounts_by_owner(owner, TokenAccountOpts(mint))
        return account_data.value[0].pubkey, None
    except Exception as e:
        swap_associated_token_address = get_associated_token_address(owner, mint)
        swap_token_account_instructions = create_associated_token_account(owner, owner, mint)
        return swap_associated_token_address, swap_token_account_instructions


def get_all_program_accs(owner):
    rpc = "https://raydium-raydium-5ad5.mainnet.rpcpool.com/"
    rpc_headers = {'authority': 'raydium-raydium-5ad5.mainnet.rpcpool.com', 'accept': '*/*',
                   'accept-language': 'en-US,en;q=0.9', 'cache-control': 'no-cache',
                   'content-type': 'application/json', 'dnt': '1', 'origin': 'https://raydium.io',
                   'pragma': 'no-cache', 'referer': 'https://raydium.io/',
                   'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                   'sec-ch-ua-mobile': '?0', 'sec-ch-ua-platform': '"Windows"', 'sec-fetch-dest': 'empty',
                   'sec-fetch-mode': 'cors', 'sec-fetch-site': 'cross-site',
                   'solana-client': 'js/0.0.0-development',
                   'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, '
                                 'like Gecko) Chrome/120.0.0.0 Safari/537.36', }
    owner = Pubkey.from_string(owner)
    ctx = Client(rpc, extra_headers=rpc_headers)
    pga = ctx.get_program_accounts(owner)
    print(json.loads(pga.to_json()))


def get_market_id_from_mint(owner, mint):
    # print('yea nigga')
    # rpc = 'https://ssc-dao.genesysgo.net'
    rpc = "https://raydium-raydium-5ad5.mainnet.rpcpool.com/"
    rpc_headers = {'authority': 'raydium-raydium-5ad5.mainnet.rpcpool.com', 'accept': '*/*',
                   'accept-language': 'en-US,en;q=0.9', 'cache-control': 'no-cache',
                   'content-type': 'application/json', 'dnt': '1', 'origin': 'https://raydium.io',
                   'pragma': 'no-cache', 'referer': 'https://raydium.io/',
                   'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                   'sec-ch-ua-mobile': '?0', 'sec-ch-ua-platform': '"Windows"', 'sec-fetch-dest': 'empty',
                   'sec-fetch-mode': 'cors', 'sec-fetch-site': 'cross-site',
                   'solana-client': 'js/0.0.0-development',
                   'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, '
                                 'like Gecko) Chrome/120.0.0.0 Safari/537.36', }
    owner = Pubkey.from_string(owner)
    sm = mint
    mint = Pubkey.from_string(mint)
    ctx = Client(rpc, extra_headers=rpc_headers)
    pga = ctx.get_program_accounts(owner, filters=[MemcmpOpts(53, sm)])
    if not json.loads(pga.to_json())['result']:
        pga = ctx.get_program_accounts(owner, filters=[MemcmpOpts(85, sm)])
    return json.loads(pga.to_json())['result'][0]['pubkey']


fc = {}


def get_shitcoin_price(client, shitcoin_address):
    mint = Pubkey.from_string(shitcoin_address)
    # pool_keys = fetch_pool_keys(str(mint))
    if shitcoin_address in fc:
        pool_keys = fc[shitcoin_address]
    else:
        pool_keys = fetch_pool_keys_personal(str(mint))
        fc[shitcoin_address] = pool_keys
    base_info = client.get_multiple_accounts_json_parsed([pool_keys['base_vault'], pool_keys['quote_vault']])
    base_i = base_info.value[0]
    quote_i = base_info.value[1]
    flipped = quote_i.data.parsed['info']['mint'] != 'So11111111111111111111111111111111111111112'
    base_amt = int(base_i.data.parsed['info']['tokenAmount']['amount'])  # 50
    quote_amt = int(quote_i.data.parsed['info']['tokenAmount']['amount'])  # 100
    to_decimal = base_i.data.parsed['info']['tokenAmount']['decimals']
    decimal_shifter = 10 ** to_decimal
    new_price = (quote_amt / base_amt) / (10 ** (9 - to_decimal))
    if flipped:
        new_price = base_amt / quote_amt
        return new_price, decimal_shifter
    return new_price, decimal_shifter


def sell_get_token_account(ctx, owner: Pubkey.from_string, mint: Pubkey.from_string):
    try:
        account_data = ctx.get_token_accounts_by_owner(owner, TokenAccountOpts(mint))
        return account_data.value[0].pubkey
    except Exception as e:
        print("Mint Token Not found, ", e)
        return None


def make_swap_instruction(amount_in: int, token_account_in: Pubkey.from_string, token_account_out: Pubkey.from_string,
                          accounts: dict, mint, ctx, owner, amount_we_want, selling=False,
                          decimal_shifter=None, maximum_sol_we_spend=0) -> Instruction:
    token_pk = mint
    account_program_id = None
    while True:
        try:
            account_program_id = ctx.get_account_info_json_parsed(token_pk)
            break
        except Exception as e:
            time.sleep(.1)
            print(e, 'problem')
            continue
    token_program_id = account_program_id.value.owner

    keys = [
        AccountMeta(pubkey=token_program_id, is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["amm_id"], is_signer=False, is_writable=True),  # just regular id we have it
        AccountMeta(pubkey=accounts["authority"], is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["open_orders"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["target_orders"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["base_vault"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["quote_vault"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=SERUM_PROGRAM_ID, is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["market_id"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["bids"], is_signer=False, is_writable=True),  # need A
        AccountMeta(pubkey=accounts["asks"], is_signer=False, is_writable=True),  # need A
        AccountMeta(pubkey=accounts["event_queue"], is_signer=False, is_writable=True),  # need A
        AccountMeta(pubkey=accounts["market_base_vault"], is_signer=False, is_writable=True),  # need A
        AccountMeta(pubkey=accounts["market_quote_vault"], is_signer=False, is_writable=True),  # need A
        AccountMeta(pubkey=accounts["market_authority"], is_signer=False, is_writable=False),  # need
        AccountMeta(pubkey=token_account_in, is_signer=False, is_writable=True),
        AccountMeta(pubkey=token_account_out, is_signer=False, is_writable=True),
        AccountMeta(pubkey=owner.pubkey(), is_signer=True, is_writable=False)
    ]
    sol_spent = int(maximum_sol_we_spend)
    # sol_spent_profit = int(sol_spent * 0.95)  # 5% slippage when selling, call this with the price of the shitcoin in
    sol_spent_profit = int(sol_spent * SLIPPAGE)
    # sol (total sol amount we want to get out of the shitcoin, price of shitcoin * how many coins we own
    data = layout.SWAP_LAYOUT.build(
        dict(
            instruction=9,
            amount_in=int(amount_in),
            min_amount_out=int(amount_we_want * decimal_shifter) if not selling else sol_spent_profit
        )
    )
    return Instruction(AMM_PROGRAM_ID, data, keys)


if __name__ == "__main__":
    print(get_liquid4('sj7CRKKcRADNv5jg9ogAvQ7EojQ2n22suXXAHVv6paD'))
