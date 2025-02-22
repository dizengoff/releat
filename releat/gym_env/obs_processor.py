"""Observation processor."""
from __future__ import annotations

import numpy as np
from numba import njit

from releat.data.simple.stats import apply_log_tail
from releat.data.simple.stats import randint
from releat.data.transformers import apply_transform


def init_raw_data(config, client, raw_data_shape, i):
    """Initialise raw data.

    Initialising raw data by reading and storing in memory the all the records
    necessary to make each observation. For example, if making predictions on a
    rolling 10s basis, and each feature is 2m, and each observation looks at 10 of these
    intervals, then we would need to load approx 6 (6 10s records in a minute)
    x 2 x 10 + 1 records.

    Run at gym environment reset

    Args:
        config (Dict(pydantic.BaseModel|dict|Any)):
            as defined in 'agent_config.py'
        client (aerospike.Client):
            client object for downloading downloading records
        raw_data_shape (dict):
            shape for each of the arrays in the observation
        i (int):
            database table index of the starting observation, i.e. records are pulled
            from i-x:i

    Returns:
        dict
            raw_data from which the observation can be build

    """
    raw_data = {}
    feat_group_inds = [x for x in raw_data_shape.keys() if x != "max"]
    for k in feat_group_inds:
        raw_data[k] = []

    for j in range(i - raw_data_shape["max"], i + 1):
        key = (
            config["aerospike"].namespace,
            config["aerospike"].set_name,
            j,
        )
        (_, _, bins) = client.get(key)
        for k in feat_group_inds:
            raw_data[k].append(bins[k])

    raw_data["date"] = bins["date"]
    raw_data["trade_price"] = bins["trade_price"]
    raw_data["date_arr"] = bins["date_arr"]

    for k in feat_group_inds:
        raw_data[k] = np.array(raw_data[k][-raw_data_shape[k] :], dtype=np.float32)

    return raw_data


def update_raw_data(config, client, raw_data_shape, raw_data, i):
    """Update raw data.

    Reads the next record and appends to raw data. Run at each gym environment step.

    Args:
        config (Dict(pydantic.BaseModel|dict|Any)):
            as defined in 'agent_config.py'
        client (aerospike.Client):
            client object for downloading downloading records
        raw_data_shape (dict):
            shape for each of the arrays in the observation
        raw_data (dict):
            raw data where the new record will be appended
        i (int):
            database table index of the next observation

    Returns:
        dict
            raw_data with the next observation appended

    """
    feat_group_inds = [x for x in raw_data_shape.keys() if x != "max"]

    key = (
        config["aerospike"].namespace,
        config["aerospike"].set_name,
        i,
    )

    (_, _, bins) = client.get(key)

    for k in feat_group_inds:
        bins[k] = np.array([bins[k]], dtype=np.float32)
        raw_data[k] = np.vstack([raw_data[k], bins[k]])[1:]

    raw_data["date"] = bins["date"]
    raw_data["trade_price"] = bins["trade_price"]
    raw_data["date_arr"] = bins["date_arr"]

    return raw_data


def get_obs(config, obs_interval, raw_data):
    """Get obs.

    # TODO make this parametric for feats + pips + multi symbol

    Gets gym observation from raw data, i.e. gets every X records depending
    on the feature timeframe

    Args:
        config (Dict(pydantic.BaseModel|dict|Any)):
            as defined in 'agent_config.py'
        obs_interval (dict):
            the timeframe of each feature group
        raw_data (dict):
            raw data

    Returns:
        dict
            gym observation (without static data such as date, positiov value, etc.)

    """
    obs = {}
    feat_group_inds = [x for x in obs_interval.keys()]
    for k in feat_group_inds:
        obs[k] = raw_data[k][:: obs_interval[k]]

    for feat_group_ind in range(len(feat_group_inds)):
        feat_ind = 0
        feat_group = config["features"][feat_group_ind]
        fc = feat_group.simple_features[feat_ind]
        feats = obs[str(feat_group_ind)][:, 0]
        feats = feats - feats[-1]

        symbol = fc.symbol
        symbol_index = config["symbol_info_index"][symbol]
        pip = config["symbol_info"][symbol_index].pip

        feats = feats[:-1] / pip
        feats = feats.reshape((-1, 1))
        for tc in fc.transforms:
            feats = apply_transform(feats, tc)

        obs[str(feat_group_ind)] = obs[str(feat_group_ind)][1:]
        obs[str(feat_group_ind)][:, 0] = feats[:, 0]
        obs[str(feat_group_ind)] = obs[str(feat_group_ind)].astype("float32")

    obs["date_arr"] = np.array(raw_data["date_arr"], dtype="float32")
    return obs


@njit("float32[:](float32[:])", nogil=True, cache=True, fastmath=True)
def scale_pos_val(pos_val):
    """Scale pos val.

    Args:
        pos_val (float)
            value of position in pips

    Returns:
        np.float
            scaled position

    """
    thresh = 0
    log_base = -1
    scalar = pos_val * np.float32(0.03)
    pos_val = apply_log_tail(pos_val, thresh, log_base)
    pos_val = pos_val / np.float32(3.0) + scalar
    return np.clip(pos_val, np.float32(-2.0), np.float32(2.0))


@njit(nogil=True, cache=True, fastmath=True)
def sample_price(min_p, max_p, pip):
    """Sample price.

    Args:
        min_p (np.float)
            min price of ticker within the action window
        max_p (np.float)
            max price of ticer within the action window
        pip (np.float)
            value of a pip, i.e. 1e-4 for EURUSD

    Returns:
        np.float
            a randomly sampled price between those values

    """
    return randint(int(min_p * 10 / pip), int(max_p * 10 / pip) + 1) * pip / 10


@njit(nogil=True, cache=True, fastmath=True)
def portfolio_to_model_input(portfolio):
    """Portfolio to model input.

    #TODO make this parametric / different ways of representing position value

    Args:
        portfolio (np.array)

    Returns:
        np.array

    """
    # v = portfolio[:, [5, 6, 9, 12]].copy()
    # v[:, 3] = scale_pos_val(v[:, 3].astype("float32"))
    # v[:, 2] = np.clip(v[:, 2], 0, 720)
    # v = np.divide(v, np.array([2.0, 1.0, 360, 1.0]))
    # v = v.flatten()
    # index 5, 12
    v = portfolio[:, 5::7].copy()
    v[:, 1] = scale_pos_val(v[:, 1].astype("float32"))
    v[:, 0] = v[:, 0] * portfolio[:, 6] / np.float32(2.0)
    v = v.flatten()

    return v


def get_curr_price(symbol_info, price):
    """Get curr price.

    number of symbols x [bid,ask]

    """
    curr_price = np.zeros((len(symbol_info), 2), dtype="float32")
    for i in range(len(symbol_info)):
        pip = symbol_info[0].pip
        curr_price[i, 0] = sample_price(price[i * 4], price[i * 4 + 1], pip)
        curr_price[i, 1] = sample_price(price[i * 4 + 2], price[i * 4 + 3], pip)

    return curr_price
