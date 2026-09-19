"""USB bulk transport for Goodix 27c6:5e0a hardware experiments.

pyusb is required only to instantiate USBProtocol (i.e. on a machine with
the device attached); importing this module never requires it.
"""


class USBProtocol:
    def __init__(self, vendor=0x27c6, product=0x5e0a, timeout=5):
        try:
            import usb.core
            import usb.util
        except ImportError as e:
            raise ImportError(
                "pyusb is required for hardware access (pip install pyusb)"
            ) from e
        self.vendor = vendor
        self.product = product
        self.device = usb.core.find(idVendor=vendor, idProduct=product)
        if self.device is None:
            raise TimeoutError(f"Device {vendor:04x}:{product:04x} not found")

        # Find interface
        cfg = self.device.get_active_configuration()
        intf = usb.util.find_descriptor(
            cfg,
            custom_match=lambda i: i.bInterfaceClass in (0x0A, 0xFF)
        )
        if intf is None:
            raise ConnectionError("Interface not found")
        self.interface_num = intf.bInterfaceNumber

        # Detach kernel driver if active
        try:
            if self.device.is_kernel_driver_active(self.interface_num):
                self.device.detach_kernel_driver(self.interface_num)
        except Exception:
            pass

        # Find endpoints
        ep_in = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: (usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN and
                                   usb.util.endpoint_type(e.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK)
        )
        ep_out = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: (usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT and
                                   usb.util.endpoint_type(e.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK)
        )
        if ep_in is None or ep_out is None:
            raise ConnectionError("Bulk endpoints not found")

        self.endpoint_in = ep_in.bEndpointAddress
        self.endpoint_out = ep_out.bEndpointAddress
        print(f"Connected: EP OUT {hex(self.endpoint_out)}, EP IN {hex(self.endpoint_in)}")

    def write(self, data: bytes, timeout: float = 5):
        timeout_ms = int(timeout * 1000) if timeout else 5000
        length = len(data)
        if length % 0x40 != 0:
            data += b"\x00" * (0x40 - (length % 0x40))
        for i in range(0, len(data), 0x40):
            self.device.write(self.endpoint_out, data[i:i+0x40], timeout_ms)

    def read(self, size: int = 0x10000, timeout: float = 5) -> bytes:
        timeout_ms = int(timeout * 1000) if timeout else 5000
        return self.device.read(self.endpoint_in, size, timeout_ms).tobytes()

    def disconnect(self, timeout: float = 5):
        pass
