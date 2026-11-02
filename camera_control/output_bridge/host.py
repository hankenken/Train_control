"""TC2 serial bench client. No command retries and no automatic camera integration."""
from __future__ import annotations

import argparse
import collections
import threading
import time


class BridgeError(RuntimeError):
    pass


class Refused(BridgeError):
    pass


class Client:
    def __init__(self, transport, *, timeout=1.0, clock=time.monotonic):
        if timeout < 1 or timeout > 10:
            raise ValueError("ACK timeout must be 1..10 seconds")
        self.transport, self.timeout, self.clock = transport, timeout, clock
        self.seq = 0
        self.closed = False
        self.lock = threading.RLock()
        self.stopping = threading.Event()
        self.worker = None
        self.done = collections.deque(maxlen=16)
        self.status_fields = {}
        self.verified = False
        self.may_have_armed = False

    @classmethod
    def open(cls, port: str, *, timeout=1.0):
        if not isinstance(port, str) or not port.strip() or "://" in port:
            raise ValueError("An explicit local COM/device name is required")
        import serial  # Optional dependency; no serial import/open for help or dry run.
        transport = serial.Serial(port=port, baudrate=115200, timeout=.02, write_timeout=.2)
        client = cls(transport, timeout=timeout)
        try:
            client.handshake()
        except BaseException:
            # Unknown protocol: close without sending TC2 actuation commands.
            transport.close()
            client.closed = True
            raise
        return client

    def _write(self, command):
        raw = (command + "\n").encode("ascii")
        if len(raw) > 64 or self.transport.write(raw) != len(raw):
            raise BridgeError("Incomplete serial write")

    def _read(self, deadline):
        while self.clock() < deadline:
            raw = self.transport.readline(192)
            if not raw:
                continue
            if len(raw) >= 192 or not raw.endswith(b"\n"):
                raise BridgeError("Truncated/oversized response")
            try:
                line = raw.decode("ascii").rstrip("\r\n")
            except UnicodeDecodeError as exc:
                raise BridgeError("Non-ASCII response") from exc
            return line
        raise BridgeError("ACK timeout; PULSE will not be retried")

    def handshake(self):
        with self.lock:
            self._write("HELLO")
            if self._read(self.clock() + self.timeout) != "READY TC2 DRV8235_I2C":
                raise BridgeError("Unsupported firmware capability")
            fields = self.status()
            self.seq = int(fields["last_seq"])
            self.verified = True
            return fields

    def _next(self):
        if self.seq >= 4294967295:
            raise BridgeError("Sequence exhausted; stop and power-cycle before a new session")
        self.seq += 1
        return self.seq

    def _queue_done(self, line):
        words = line.split()
        if len(words) != 3 or words[0] != "DONE" or not words[1].isdigit() or not words[2].isdigit():
            return False
        seq, ch = int(words[1]), int(words[2])
        if not 1 <= seq <= self.seq or not 0 <= ch <= 3:
            raise BridgeError("Invalid DONE")
        self.done.append((seq, ch))
        return True

    def status(self):
        with self.lock:
            if self.closed:
                raise BridgeError("Connection is closed")
            try:
                self._write("STATUS")
                deadline = self.clock() + self.timeout
                while True:
                    line = self._read(deadline)
                    if self._queue_done(line):
                        continue
                    prefix = "STATUS TC2 DRV8235_I2C "
                    if not line.startswith(prefix):
                        raise BridgeError("Unexpected STATUS response")
                    fields = dict(word.split("=", 1) for word in line[len(prefix):].split())
                    for key in ("armed", "active", "last_seq", "hb_age_ms", "fault"):
                        if key not in fields:
                            raise BridgeError("Missing STATUS field")
                    if fields["armed"] not in ("0", "1") or int(fields["active"]) not in range(-1, 4):
                        raise BridgeError("Invalid STATUS state")
                    if not 0 <= int(fields["last_seq"]) <= 4294967295:
                        raise BridgeError("Invalid sequence")
                    self.status_fields = fields
                    return dict(fields)
            except Exception as exc:
                self._fault_close()
                if isinstance(exc, BridgeError):
                    raise
                raise BridgeError(str(exc)) from exc

    def _command(self, kind, suffix=""):
        with self.lock:
            if self.closed:
                raise BridgeError("Connection is closed")
            if not self.verified:
                raise BridgeError("HELLO/STATUS handshake is required")
            try:
                seq = self._next()
                self._write(f"{kind} {seq}" + (" " + suffix if suffix else ""))
                deadline = self.clock() + self.timeout
                while True:
                    line = self._read(deadline)
                    if self._queue_done(line):
                        continue
                    if line == f"OK {seq} {kind}":
                        return seq
                    if line.startswith(f"ERR {seq} "):
                        reason = line.split(" ", 2)[2]
                        if reason in ("BUSY", "COOLDOWN", "DISARMED", "VM_RESET_REQUIRED"):
                            raise Refused(reason)
                        raise BridgeError(reason)
                    raise BridgeError("Unexpected or stale command response")
            except Refused:
                raise
            except Exception as exc:
                self._fault_close()
                if isinstance(exc, BridgeError):
                    raise
                raise BridgeError(str(exc)) from exc

    def heartbeat(self):
        return self._command("HB")

    def start_heartbeats(self):
        if self.closed:
            raise BridgeError("Connection is closed")
        if self.worker is not None:
            return
        self.heartbeat()
        def run():
            while not self.stopping.wait(.1):
                try:
                    self.heartbeat()
                except BridgeError:
                    self._fault_close()
                    return
        self.worker = threading.Thread(target=run, name="tc2-heartbeat", daemon=True)
        self.worker.start()

    def arm(self):
        with self.lock:
            self.heartbeat()  # Fresh immediately before potentially delayed ACK.
            self.may_have_armed = True
            return self._command("ARM")

    def pulse(self, channel, direction, milliseconds):
        if type(channel) is not int or channel not in range(4):
            raise ValueError("channel must be 0..3")
        if direction not in ("P", "N") or type(milliseconds) is not int or not 20 <= milliseconds <= 100:
            raise ValueError("direction P/N, width 20..100 ms required")
        with self.lock:
            self.heartbeat()
            return self._command("PULSE", f"{channel} {direction} {milliseconds}")

    def wait_done(self, seq, channel, *, timeout=1.0):
        # Does not resend PULSE on timeout or loss of DONE.
        deadline = self.clock() + timeout
        with self.lock:
            try:
                while True:
                    if (seq, channel) in self.done:
                        self.done.remove((seq, channel))
                        return
                    self._queue_done_or_fail(self._read(deadline))
            except Exception as exc:
                self._fault_close()
                if isinstance(exc, BridgeError):
                    raise
                raise BridgeError(str(exc)) from exc

    def _queue_done_or_fail(self, line):
        if not self._queue_done(line):
            raise BridgeError("Unexpected response while waiting for DONE")

    def stop(self):
        return self._command("STOP")

    def _fault_close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            self.stopping.set()
            try:
                if self.may_have_armed:
                    self.seq = min(self.seq + 1, 4294967295)
                    self._write(f"STOP {self.seq}")  # Best effort once, no ACK wait/retry.
            except Exception:
                pass
            finally:
                self.transport.close()

    def close(self):
        self._fault_close()
        if self.worker and self.worker is not threading.current_thread():
            self.worker.join(timeout=1.5)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="Explicit Windows COM port; no automatic port probing")
    parser.add_argument("--status", action="store_true", help="Read HELLO/STATUS only")
    parser.add_argument("--pulse", nargs=3, metavar=("CHANNEL", "P_OR_N", "MS"))
    parser.add_argument("--execute", action="store_true", help="Open hardware and run one bench pulse")
    args = parser.parse_args(argv)
    if args.status and args.pulse:
        parser.error("Choose --status or --pulse")
    if not args.status and not args.execute:
        print("Dry run: no serial import, COM port, ARM, or output. Use --status for read-only inspection.")
        return 0
    if not args.port:
        parser.error("--port is required to open hardware")
    if args.execute and not args.pulse:
        parser.error("--execute requires --pulse CHANNEL P_OR_N MS")
    values = None
    if args.pulse:
        try:
            ch, direction, width = int(args.pulse[0]), args.pulse[1], int(args.pulse[2])
            if ch not in range(4) or direction not in ("P", "N") or not 20 <= width <= 100:
                raise ValueError()
            values = ch, direction, width
        except ValueError:
            parser.error("Pulse requires channel 0..3, P/N, width 20..100 ms")
    client = Client.open(args.port)
    try:
        if args.status:
            print(client.status_fields)
        else:
            client.start_heartbeats()
            client.arm()
            seq = client.pulse(*values)
            client.wait_done(seq, values[0])
            client.stop()
            print(f"DONE {seq} {values[0]}: electrical command completed; mechanical position unverified")
    finally:
        if args.status:
            # Status mode must not send STOP, HB, or ARM on normal close.
            client.closed = True
            client.transport.close()
        else:
            client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
