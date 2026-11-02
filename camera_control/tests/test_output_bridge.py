import collections
import contextlib
import io
import unittest
from camera_control.output_bridge.host import Client, BridgeError, Refused, main


class Clock:
    def __init__(self): self.now = 0
    def __call__(self): self.now += .01; return self.now


class Serial:
    def __init__(self, *, last_seq=0, fault="NONE", drop=None, reject=None):
        self.writes = []; self.responses = collections.deque(); self.closed = False
        self.last_seq = last_seq; self.fault = fault; self.drop = drop; self.reject = reject
    def write(self, raw):
        self.writes.append(raw.decode().strip()); w = self.writes[-1].split(); k = w[0]
        if k == self.drop: return len(raw)
        if k == "HELLO": self.responses.append(b"READY TC2 DRV8235_I2C\n")
        elif k == "STATUS":
            self.responses.append(f"STATUS TC2 DRV8235_I2C armed=0 active=-1 last_seq={self.last_seq} hb_age_ms=-1 fault={self.fault} vm_ready=1 pending=0\n".encode())
        else:
            self.last_seq = int(w[1]); self.responses.append((f"ERR {w[1]} {self.reject}" if k == "PULSE" and self.reject else f"OK {w[1]} {k}").encode() + b"\n")
            if k == "PULSE" and not self.reject: self.responses.append(f"DONE {w[1]} {w[2]}\n".encode())
        return len(raw)
    def readline(self, size): return self.responses.popleft() if self.responses else b""
    def close(self): self.closed = True


def connect(**kwargs):
    serial = Serial(**kwargs); client = Client(serial, clock=Clock()); client.handshake()
    return serial, client


class BridgeTests(unittest.TestCase):
    def test_dry_run_opens_nothing(self):
        with contextlib.redirect_stdout(io.StringIO()) as out: self.assertEqual(main([]), 0)
        self.assertIn("no serial import", out.getvalue())

    def test_status_and_handshake_are_read_only(self):
        s, c = connect(last_seq=17); self.assertEqual(c.seq, 17); c.status(); c.close()
        self.assertEqual(s.writes, ["HELLO", "STATUS", "STATUS"])

    def test_unique_sequences_and_electrical_done(self):
        s, c = connect(last_seq=9); c.arm(); seq = c.pulse(2, "N", 75); c.wait_done(seq, 2); c.stop(); c.close()
        self.assertEqual(seq, 13)
        self.assertEqual(len([x for x in s.writes if x.startswith("PULSE")]), 1)
        sequences = [int(x.split()[1]) for x in s.writes if x.split()[0] not in ("HELLO", "STATUS")]
        self.assertEqual(sequences, sorted(set(sequences)))

    def test_lost_pulse_ack_never_retries(self):
        s, c = connect(drop="PULSE"); c.arm()
        with self.assertRaises(BridgeError): c.pulse(0, "P", 50)
        self.assertTrue(s.closed)
        self.assertEqual([x for x in s.writes if x.startswith("PULSE")], ["PULSE 4 0 P 50"])
        self.assertEqual(s.writes[-1], "STOP 5")

    def test_lost_done_stops_once(self):
        s, c = connect(); c.arm(); seq = c.pulse(0, "P", 50); s.responses.clear()
        with self.assertRaises(BridgeError): c.wait_done(seq, 0)
        self.assertTrue(s.closed); self.assertEqual(s.writes[-1], "STOP 5")

    def test_busy_and_cooldown_do_not_retry(self):
        for reason in ("BUSY", "COOLDOWN"):
            s, c = connect(reject=reason); c.arm()
            with self.assertRaises(Refused): c.pulse(0, "P", 50)
            self.assertFalse(c.closed); self.assertEqual(s.writes[-1], "PULSE 4 0 P 50"); c.close()

    def test_wrong_protocol_will_not_arm(self):
        s = Serial(); c = Client(s, clock=Clock()); s.drop = "HELLO"
        s.responses.append(b"READY TC1 GPIO\n")
        with self.assertRaises(BridgeError): c.handshake()
        self.assertEqual(s.writes, ["HELLO"])
        with self.assertRaises(BridgeError): c.arm()
        self.assertNotIn("ARM", " ".join(s.writes))

    def test_invalid_pulse_has_no_serial_effect(self):
        s, c = connect(); before = list(s.writes)
        for ch, d, ms in ((True,"P",50),(4,"P",50),(0,"X",50),(0,"P",101),(0,"P",19)):
            with self.assertRaises(ValueError): c.pulse(ch,d,ms)
        self.assertEqual(s.writes, before)

    def test_full_sequence_space_still_sends_stopping_stale_seq(self):
        s, c = connect(last_seq=4294967294); c.may_have_armed = True; c.heartbeat()
        with self.assertRaises(BridgeError): c.heartbeat()
        self.assertEqual(s.writes[-1], "STOP 4294967295")

    def test_malformed_response_fault_closes_without_retry(self):
        s, c = connect(); c.arm(); s.responses.append(b"garbage\n")
        with self.assertRaises(BridgeError): c.pulse(0,"P",50)
        self.assertTrue(c.closed); self.assertTrue(s.writes[-1].startswith("STOP"))

    def test_status_queues_done(self):
        s,c=connect();c.arm();seq=c.pulse(1,"P",20);c.status();c.wait_done(seq,1);c.close()


if __name__ == "__main__": unittest.main()
