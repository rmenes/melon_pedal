#!/usr/bin/env python3
"""melon-ble: Bluetooth LE bridge between the Melon Pedal Android app and melon-pedald.

The phone talks to one GATT service (a "UART over BLE", like Nordic's NUS):

  service  6d656c6f-6e70-6564-616c-000000000000   "Melon Pedal"
  RX       6d656c6f-6e70-6564-616c-000000000001   write / write-without-response   phone -> pedal
  TX       6d656c6f-6e70-6564-616c-000000000002   notify                           pedal -> phone

Both directions carry the JSON lines of melon-pedald's remote API (see
melon_pedald/remote.py). A message may be split over several BLE packets; the
"\\n" at the end of each JSON object marks where it ends. This bridge does not
understand the messages, it only moves lines between BLE and 127.0.0.1:5601.

Needs (Raspberry Pi OS): sudo apt install bluez python3-dbus python3-gi
Run:   python3 melon_ble.py            (melon-pedald must be running with its remote API)
"""
import argparse
import socket
import sys

import dbus
import dbus.exceptions
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib

BLUEZ = "org.bluez"
OM_IFACE = "org.freedesktop.DBus.ObjectManager"
PROP_IFACE = "org.freedesktop.DBus.Properties"
ADAPTER_IFACE = "org.bluez.Adapter1"
GATT_MANAGER_IFACE = "org.bluez.GattManager1"
ADV_MANAGER_IFACE = "org.bluez.LEAdvertisingManager1"
SERVICE_IFACE = "org.bluez.GattService1"
CHRC_IFACE = "org.bluez.GattCharacteristic1"
ADV_IFACE = "org.bluez.LEAdvertisement1"

SERVICE_UUID = "6d656c6f-6e70-6564-616c-000000000000"
RX_UUID = "6d656c6f-6e70-6564-616c-000000000001"
TX_UUID = "6d656c6f-6e70-6564-616c-000000000002"

ROOT = "/org/melon/pedal"
MAX_LINE = 16384          # longest JSON line accepted from the phone
DEFAULT_MTU = 23          # BLE minimum; the real value arrives with the phone's first write


def log(*a):
    print(*a, flush=True)


class NotSupported(dbus.exceptions.DBusException):
    _dbus_error_name = "org.bluez.Error.NotSupported"


class InvalidArgs(dbus.exceptions.DBusException):
    _dbus_error_name = "org.freedesktop.DBus.Error.InvalidArgs"


# --------------------------------------------------------------------- framing
class LineBuffer:
    """Collects bytes and returns complete lines (without the newline)."""

    def __init__(self, limit=MAX_LINE):
        self.buf = b""
        self.limit = limit

    def feed(self, data):
        self.buf += data
        lines = []
        while b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            if line.strip():
                lines.append(line)
        if len(self.buf) > self.limit:      # garbage without newlines: start over
            self.buf = b""
        return lines


def chunks(data, mtu):
    """Split bytes into notification-sized pieces (ATT payload = MTU - 3, at most 512)."""
    size = max(20, min(mtu - 3, 512))
    return [data[i:i + size] for i in range(0, len(data), size)]


# ------------------------------------------------------------------ GATT objects
class Application(dbus.service.Object):
    def __init__(self, bus):
        self.path = ROOT
        self.services = []
        super().__init__(bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method(OM_IFACE, out_signature="a{oa{sa{sv}}}")
    def GetManagedObjects(self):
        objs = {}
        for s in self.services:
            objs[s.get_path()] = s.get_properties()
            for c in s.characteristics:
                objs[c.get_path()] = c.get_properties()
        return objs


class Service(dbus.service.Object):
    def __init__(self, bus, index, uuid):
        self.path = f"{ROOT}/service{index}"
        self.uuid = uuid
        self.characteristics = []
        super().__init__(bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        return {SERVICE_IFACE: {
            "UUID": self.uuid,
            "Primary": True,
            "Characteristics": dbus.Array([c.get_path() for c in self.characteristics], signature="o"),
        }}

    @dbus.service.method(PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != SERVICE_IFACE:
            raise InvalidArgs()
        return self.get_properties()[SERVICE_IFACE]


class Characteristic(dbus.service.Object):
    def __init__(self, bus, index, uuid, flags, service):
        self.path = f"{service.path}/char{index}"
        self.uuid = uuid
        self.flags = flags
        self.service = service
        super().__init__(bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        return {CHRC_IFACE: {
            "Service": self.service.get_path(),
            "UUID": self.uuid,
            "Flags": dbus.Array(self.flags, signature="s"),
            "Descriptors": dbus.Array([], signature="o"),
        }}

    @dbus.service.method(PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != CHRC_IFACE:
            raise InvalidArgs()
        return self.get_properties()[CHRC_IFACE]

    @dbus.service.method(CHRC_IFACE, in_signature="a{sv}", out_signature="ay")
    def ReadValue(self, options):
        raise NotSupported()

    @dbus.service.method(CHRC_IFACE, in_signature="aya{sv}")
    def WriteValue(self, value, options):
        raise NotSupported()

    @dbus.service.method(CHRC_IFACE)
    def StartNotify(self):
        raise NotSupported()

    @dbus.service.method(CHRC_IFACE)
    def StopNotify(self):
        raise NotSupported()

    @dbus.service.signal(PROP_IFACE, signature="sa{sv}as")
    def PropertiesChanged(self, interface, changed, invalidated):
        pass


class RxCharacteristic(Characteristic):
    """Phone -> pedal."""

    def __init__(self, bus, index, service, bridge):
        super().__init__(bus, index, RX_UUID, ["write", "write-without-response"], service)
        self.bridge = bridge

    def WriteValue(self, value, options):
        mtu = options.get("mtu")
        if mtu:
            self.bridge.mtu = int(mtu)
        self.bridge.from_phone(bytes(value))


class TxCharacteristic(Characteristic):
    """Pedal -> phone (notifications)."""

    def __init__(self, bus, index, service, bridge):
        super().__init__(bus, index, TX_UUID, ["notify"], service)
        self.notifying = False
        self.bridge = bridge

    def StartNotify(self):
        if not self.notifying:
            self.notifying = True
            log("phone subscribed")

    def StopNotify(self):
        if self.notifying:
            self.notifying = False
            self.bridge.mtu = DEFAULT_MTU
            log("phone unsubscribed / disconnected")

    def notify(self, data):
        self.PropertiesChanged(CHRC_IFACE, {"Value": dbus.Array(data, signature="y")}, [])


class Advertisement(dbus.service.Object):
    def __init__(self, bus, name, with_name=True):
        self.path = f"{ROOT}/adv0"
        self.name = name
        self.with_name = with_name
        super().__init__(bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        props = {
            "Type": "peripheral",
            "ServiceUUIDs": dbus.Array([SERVICE_UUID], signature="s"),
        }
        if self.with_name:
            props["LocalName"] = dbus.String(self.name)
        return {ADV_IFACE: props}

    @dbus.service.method(PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != ADV_IFACE:
            raise InvalidArgs()
        return self.get_properties()[ADV_IFACE]

    @dbus.service.method(ADV_IFACE, in_signature="", out_signature="")
    def Release(self):
        log("advertisement released by BlueZ")


# ------------------------------------------------------------------ the bridge
class Bridge:
    def __init__(self, host, port):
        self.addr = (host, port)
        self.sock = None
        self.watch = None
        self.mtu = DEFAULT_MTU
        self.tx = None                    # TxCharacteristic
        self.from_phone_lines = LineBuffer()
        self.retry_scheduled = False
        self.warned = False

    # TCP side -------------------------------------------------------------
    def connect(self):
        self.retry_scheduled = False
        try:
            s = socket.create_connection(self.addr, timeout=2)
        except OSError:
            if not self.warned:
                log(f"waiting for melon-pedald remote API on {self.addr[0]}:{self.addr[1]} ...")
                self.warned = True
            self._retry()
            return False
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s.settimeout(2)
        self.sock = s
        self.warned = False
        self.watch = GLib.io_add_watch(s.fileno(), GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR, self._on_tcp)
        log("connected to melon-pedald")
        if self.tx and self.tx.notifying:   # pedald restarted while a phone is connected: resync it
            self._send_tcp(b'{"op":"hello","app":"melon-ble","proto":1}')
        return False

    def _retry(self):
        if not self.retry_scheduled:
            self.retry_scheduled = True
            GLib.timeout_add_seconds(2, self.connect)

    def _drop_tcp(self):
        if self.watch:
            GLib.source_remove(self.watch)
            self.watch = None
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
            log("lost melon-pedald")
            self.to_phone(b'{"ev":"error","msg":"pedal controller restarting"}\n')
        self._retry()

    def _on_tcp(self, fd, cond):
        try:
            data = self.sock.recv(65536) if cond & GLib.IO_IN else b""
        except OSError:
            data = b""
        if not data:
            self.watch = None             # returning False removes this watch
            self._drop_tcp()
            return False
        self.to_phone(data)
        return True

    def _send_tcp(self, line):
        if not self.sock:
            self.to_phone(b'{"ev":"error","msg":"pedal controller not running"}\n')
            return
        try:
            self.sock.sendall(line + b"\n")
        except OSError:
            self._drop_tcp()

    # BLE side -------------------------------------------------------------
    def from_phone(self, data):
        for line in self.from_phone_lines.feed(data):
            self._send_tcp(line)

    def to_phone(self, data):
        if not (self.tx and self.tx.notifying):
            return
        for piece in chunks(data, self.mtu):
            self.tx.notify(piece)


# ------------------------------------------------------------------ BlueZ setup
def find_adapter(bus):
    om = dbus.Interface(bus.get_object(BLUEZ, "/"), OM_IFACE)
    for path, ifaces in om.GetManagedObjects().items():
        if GATT_MANAGER_IFACE in ifaces and ADV_MANAGER_IFACE in ifaces:
            return path
    return None


class Registrar:
    """Registers the GATT app and the advertisement; again whenever bluetoothd restarts."""

    def __init__(self, bus, app, name):
        self.bus = bus
        self.app = app
        self.name = name
        self.adv = Advertisement(bus, name, with_name=True)

    def register(self):
        adapter = find_adapter(self.bus)
        if not adapter:
            log("no Bluetooth LE adapter found (is bluetooth.service running? `rfkill unblock bluetooth`?)")
            GLib.timeout_add_seconds(5, self.register)
            return False
        obj = self.bus.get_object(BLUEZ, adapter)
        props = dbus.Interface(obj, PROP_IFACE)
        try:
            props.Set(ADAPTER_IFACE, "Powered", dbus.Boolean(True))
            props.Set(ADAPTER_IFACE, "Alias", dbus.String(self.name))
        except dbus.exceptions.DBusException as e:
            log(f"could not power on / rename the adapter: {e.get_dbus_message()}")
        gatt = dbus.Interface(obj, GATT_MANAGER_IFACE)
        gatt.RegisterApplication(self.app.get_path(), {},
                                 reply_handler=lambda: log(f"GATT service registered on {adapter}"),
                                 error_handler=lambda e: log(f"GATT registration failed: {e}"))
        self._advertise(obj)
        return False

    def _advertise(self, adapter_obj):
        mgr = dbus.Interface(adapter_obj, ADV_MANAGER_IFACE)

        def failed(e):
            if self.adv.with_name:        # 128-bit UUID + name may not fit in 31 bytes: try without the name
                log(f"advertising with name failed ({e}); retrying without it")
                self.adv.with_name = False
                self._advertise(adapter_obj)
            else:
                log(f"advertising failed: {e}")

        mgr.RegisterAdvertisement(self.adv.get_path(), {},
                                  reply_handler=lambda: log(f"advertising as \"{self.name}\""),
                                  error_handler=failed)

    def on_bluez_owner(self, owner):
        if owner:
            log("bluetoothd is up")
            self.adv.with_name = True
            GLib.idle_add(self.register)


def main():
    ap = argparse.ArgumentParser(description="Bluetooth LE bridge for the Melon Pedal app")
    ap.add_argument("--name", default="Melon Pedal", help="Bluetooth name")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5601, help="melon-pedald remote API port")
    args = ap.parse_args()

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    bridge = Bridge(args.host, args.port)
    app = Application(bus)
    service = Service(bus, 0, SERVICE_UUID)
    rx = RxCharacteristic(bus, 0, service, bridge)
    tx = TxCharacteristic(bus, 1, service, bridge)
    service.characteristics += [rx, tx]
    app.services.append(service)
    bridge.tx = tx

    reg = Registrar(bus, app, args.name)
    bus.watch_name_owner(BLUEZ, reg.on_bluez_owner)   # registers now and after every bluetoothd restart
    bridge.connect()

    loop = GLib.MainLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        pass
    log("bye")
    return 0


if __name__ == "__main__":
    sys.exit(main())
