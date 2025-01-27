from eth_async.data.models import RawContract, DefaultABIs
from eth_async.utils.utils import read_json
from eth_async.classes import Singleton

from data.config import ABIS_DIR


class Contracts(Singleton):
    KODIAK = RawContract(
        title='kodiak',
        address='0x496e305C03909ae382974cAcA4c580E1BF32afBE',
        abi=read_json(path=(ABIS_DIR, 'kodiak_abi.json'))
    )

    iBGT = RawContract(
        title='ibgt',
        address='0x46eFC86F0D7455F135CC9df501673739d513E982',
        abi=read_json(path=(ABIS_DIR, 'default_abi.json'))
    )

    WBERA = RawContract(
        title='wbera',
        address='0x7507c1dc16935B82698e4C63f2746A2fCf994dF8',
        abi=read_json(path=(ABIS_DIR, 'default_abi.json'))
    )

    ISLAND_ROUTER = RawContract(
        title='island_router',
        address='0x5E51894694297524581353bc1813073C512852bf',
        abi=read_json(path=(ABIS_DIR, 'island_router_abi.json'))
    )

    KODIAK_VAULT = RawContract(
        title='kodiak_vault',
        address='0x7fd165B73775884a38AA8f2B384A53A3Ca7400E6',
        abi=read_json(path=(ABIS_DIR, 'kodiak_vault_abi.json'))
    )

    BARTIO_STATION = RawContract(
        title='bartio_station',
        address='0x7b15eeC57C60f8B68dF2b143c2CA5a772E787e86',
        abi=read_json(path=(ABIS_DIR, 'bartio_station.json'))
    )

    BGT = RawContract(
        title='bgt',
        address='0xbDa130737BDd9618301681329bF2e46A016ff9Ad',
        abi=read_json(path=(ABIS_DIR, 'bgt_abi.json'))
    )