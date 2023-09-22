"""Start and stop external apps.

Utility function for starting and stopping other open source applications:
- MetaTrader5
- ray
- Aerospike
"""
from __future__ import annotations

import os
import shlex
import signal
import subprocess

import ray

from releat.utils.logging import get_logger

logger = get_logger(__name__)


def start_blocking_process(cmd_str, blocking=True):
    """Start process.

    Args:
        cmd_str (str):
            bash command to run as a single string, i.e. 'asinfo -v STATUS'
        blocking (bool):
            True is the process should block the current terminal, otherwise
            process is opened in background

    Returns:
        process object

    """
    cmd_str = shlex.split(cmd_str)
    p = subprocess.Popen(
        cmd_str,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        bufsize=1,
        shell=False,
        # preexec_fn=os.setsid,
    )
    if blocking:
        p.wait()
    else:
        return p


def get_pids(name):
    """Get process ids.

    Gets the process IDs based on the process name. Process name must be an exact match.
    See running processes by first running 'ps -A' to list all processes.

    Args:
        name (str):
            name of the process

    Returns:
        list:
            process ids

    """
    try:
        return list(map(int, subprocess.check_output(["pidof", name]).split()))
    except Exception:
        return []


def kill_processes(pids):
    """Kills process.

    Kills process based on process ids

    Args:
        pids (list):
            list of process ids

    Returns:
        None

    """
    if len(pids) > 0:
        for pid in pids:
            os.kill(pid, signal.SIGTERM)


def start_aerospike():
    """Start Aerospike."""
    res = subprocess.run("asinfo -v STATUS", capture_output=True, text=True, shell=True)
    if "ERROR" in res.stdout != "":
        cmd_str = "asd --config-file ./infrastructure/aerospike/aerospike.conf"
        _ = start_blocking_process(cmd_str, blocking=False)
        logger.info("Aerospike started")
    else:
        logger.info("Aerospike already started")


def stop_aerospike():
    """Stop Aerospike."""
    pids = get_pids("asd")
    kill_processes(pids)
    logger.info("Aerospike stopped")


def start_mt5():
    """Start MetaTrader5."""
    cmd_str = 'wine "/root/.wine/drive_c/Program Files/MetaTrader 5/terminal64.exe"'
    logger.debug(cmd_str)
    _ = start_blocking_process(cmd_str, blocking=False)
    logger.info("MT5 started")


def stop_mt5():
    """Stop MetaTrader5."""
    pids = get_pids("terminal64.exe")
    kill_processes(pids)
    logger.info("MetaTrader5 stopped")


def start_ray():
    """Start ray."""
    try:
        ray.init(address="auto")
        logger.info("Ray already started")
    except ConnectionError:
        import tensorflow as tf

        num_cpus = os.cpu_count()
        num_gpus = len(tf.config.list_physical_devices("GPU"))

        # TODO should I be specifying the ports?
        cmd_str = f"ray start --head --num-cpus={num_cpus} --num-gpus={num_gpus} "
        logger.debug(cmd_str)
        _ = start_blocking_process(cmd_str, blocking=False)
        logger.info("Ray started")


def stop_ray():
    """Stop ray."""
    _ = start_blocking_process("ray stop", blocking=False)
    logger.info("Ray stopped")


def start_services():
    """Start all services."""
    start_aerospike()
    start_mt5()
    start_ray()


def stop_services():
    """Stop all services."""
    stop_aerospike()
    stop_mt5()
    stop_ray()
