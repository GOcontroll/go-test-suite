"""CAN bus test — adapted from go-test-can"""

import can
import netifaces


def run():
    ifaces = netifaces.interfaces()
    test_pass = True

    if "can0" in ifaces and "can1" in ifaces:
        with can.Bus(interface="socketcan", channel="can0") as bus1:
            with can.Bus(interface="socketcan", channel="can1") as bus2:
                bus1.send(can.Message(arbitration_id=1, data=[1]))
                bus2.send(can.Message(arbitration_id=2, data=[2]))
                if bus2.recv(timeout=1) is None or bus1.recv(timeout=1) is None:
                    test_pass = False
                    print("ERR: No communication between can0 and can1")
    else:
        test_pass = False
        print("ERR: missing can interfaces can0 and/or can1")

    if "can2" in ifaces and "can3" in ifaces:
        with can.Bus(interface="socketcan", channel="can2") as bus3:
            with can.Bus(interface="socketcan", channel="can3") as bus4:
                bus3.send(can.Message(arbitration_id=3, data=[3]))
                bus4.send(can.Message(arbitration_id=4, data=[4]))
                if bus4.recv(timeout=1) is None or bus3.recv(timeout=1) is None:
                    test_pass = False
                    print("ERR: No communication between can2 and can3")
    else:
        print("NOTE: only 2 CAN interfaces")

    if test_pass:
        print("PASS: All CAN busses functioning!")
    else:
        print("FAIL: CAN test failed")

    return test_pass
