"""CAN bus test"""

import time
import can
import netifaces

_counter = [0]


def _recv_matching(bus, arb_id, timeout=1.0):
    """Receive until a frame with the expected arb_id arrives, or timeout expires.
    Silently discards any frames with a different ID (stale from a previous run)."""
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        msg = bus.recv(timeout=remaining)
        if msg is None:
            return False
        if msg.arbitration_id == arb_id:
            return True


def _test_pair(ch_a, ch_b, id_a, id_b):
    """Bidirectional test: ch_a sends id_a, ch_b sends id_b; verify each receives the other."""
    with can.Bus(interface="socketcan", channel=ch_a) as bus_a:
        with can.Bus(interface="socketcan", channel=ch_b) as bus_b:
            while bus_a.recv(timeout=0) is not None:
                pass
            while bus_b.recv(timeout=0) is not None:
                pass
            bus_a.send(can.Message(arbitration_id=id_a, data=[0x55], is_extended_id=False))
            bus_b.send(can.Message(arbitration_id=id_b, data=[0xAA], is_extended_id=False))
            return (_recv_matching(bus_b, id_a) and _recv_matching(bus_a, id_b))


def run():
    _counter[0] = (_counter[0] % 255) + 1
    c = _counter[0]

    ifaces = netifaces.interfaces()
    test_pass = True

    if "can0" in ifaces and "can1" in ifaces:
        if not _test_pair("can0", "can1", c, c + 256):
            test_pass = False
    else:
        test_pass = False

    if "can2" in ifaces and "can3" in ifaces:
        if not _test_pair("can2", "can3", c + 512, c + 768):
            test_pass = False

    return test_pass
