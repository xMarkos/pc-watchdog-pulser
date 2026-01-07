import usb.core
import usb.util
import time
from typing import Any, cast

device_search_args = {
    'idVendor': 0x16c0,
    'idProduct': 0x05df,
    'manufacturer': 'xmarkos.eu',
    'product': 'Watchdog',
}

REQUEST_TYPE_SEND_VENDOR = usb.util.build_request_type(usb.util.CTRL_OUT, usb.util.CTRL_TYPE_VENDOR, usb.util.CTRL_RECIPIENT_DEVICE)
REQUEST_TYPE_SEND_CLASS = usb.util.build_request_type(usb.util.CTRL_OUT, usb.util.CTRL_TYPE_CLASS, usb.util.CTRL_RECIPIENT_DEVICE)
REQUEST_TYPE_RECEIVE_CLASS = usb.util.build_request_type(usb.util.CTRL_IN, usb.util.CTRL_TYPE_CLASS, usb.util.CTRL_RECIPIENT_DEVICE)

# Constants used for sending data using the CLASS protocol (data appears in DigiUSB buffer)
USBRQ_HID_GET_REPORT = 0x01
USBRQ_HID_SET_REPORT = 0x09
USB_HID_REPORT_TYPE_FEATURE = 0x03

# Constants used for sending data using the VENDOR protocol (custom commands)
USBRQ_PING = 1
USBRQ_SET_CONFVAR = 2

# Configuration variable indexes for USBRQ_SET_CONFVAR
CONFVAR_BRIGHTNESS = 1
CONFVAR_GRACE_PERIOD = 2

# Constants controlling this program (i.e. configuration)
PULSE_FREQUENCY_SECONDS = 10
PULSE_TIMEOUT_SECONDS = 15
DEVICE_LED_BRIGHTNESS = 1


class WatchdogUsbDevice(object):

	_device: None | usb.core.Device

	def __init__(self, device_search_args: dict[str, Any]) -> None:
		self.device_search_args = device_search_args

	def __str__(self) -> str:
		return f'{self._device!s}'

	@property
	def device(self) -> usb.core.Device:
		if self._device is None:
			raise usb.core.USBError("Device not found")

		return self._device

	def find_device(self):
		self._device = cast(usb.core.Device | None, usb.core.find(**self.device_search_args, find_all=False))

	def check_device(self):
		_ = self.device

	def write(self, data: str):
		'''
		Send string to the USB device. String is sent byte by byte, and must only contain values < 0xff.
		
		:param data: The string to send.
		:type data: str
		'''

		for c in data:
			self.write_byte(ord(c))

	def write_byte(self, data: int):
		'''
		Send 1 byte of data to the USB device.
		
		:param data: The byte to send.
		:type data: int
		'''

		value = data & 0xFF
		assert value == data, "Data out of range"

		self.device.ctrl_transfer(bmRequestType=REQUEST_TYPE_SEND_CLASS,
		                          bRequest=USBRQ_HID_SET_REPORT,
		                          wValue=(USB_HID_REPORT_TYPE_FEATURE << 8) | 0,
		                          wIndex=value,
		                          data_or_wLength=[])

		time.sleep(0.01)

	def read(self, count=50):
		'''
		Read string, byte by byte from the USB device.
		
		:param count: The maximum length of data to attempt to read.
		'''

		text = ''

		for _ in range(count):
			result = self.device.ctrl_transfer(
			    bmRequestType=REQUEST_TYPE_RECEIVE_CLASS,
			    bRequest=USBRQ_HID_GET_REPORT,
			    data_or_wLength=1,
			)

			if (not len(result)):
				break

			text += chr(result[0])
			time.sleep(0.01)

		return text

	def send_vendor_command(self, cmd: int, value: int = 0, index: int = 0):
		self.device.ctrl_transfer(bmRequestType=REQUEST_TYPE_SEND_VENDOR, bRequest=cmd, wValue=value, wIndex=index, data_or_wLength=[])

	def set_confvar(self, confvar: int, value: int):
		self.send_vendor_command(cmd=USBRQ_SET_CONFVAR, index=confvar, value=value)

	def set_led_brightness(self, value: int):
		self.set_confvar(CONFVAR_BRIGHTNESS, value)

	def set_grace_period(self, value: int):
		self.set_confvar(CONFVAR_GRACE_PERIOD, value)


device = WatchdogUsbDevice(device_search_args)

try:
	while True:
		device.find_device()
		print(f'{device=!s}')

		try:
			device.check_device()
			device.set_led_brightness(DEVICE_LED_BRIGHTNESS)
			#device.set_confvar(CONFVAR_GRACE_PERIOD, 30)

			last_pulse = 0
			last_minutes = ''

			while True:
				if len(value := device.read()):
					print(value, end='', flush=True)

				now = time.time()
				now_struct = time.localtime()
				now_minutes = now_struct.tm_min // 5 * 5

				if now_minutes != last_minutes:
					last_minutes = now_minutes
					print(f'\n[{time.strftime("%H:%M", now_struct)}] ', end='', flush=True)

				if now - last_pulse > PULSE_FREQUENCY_SECONDS:
					last_pulse = now
					device.send_vendor_command(USBRQ_PING, PULSE_TIMEOUT_SECONDS)

				time.sleep(0.1)
		except (usb.core.USBError) as e:
			print(f'Error: {e}')
			time.sleep(5)
except KeyboardInterrupt:
	# Important: this does not handle SIGKILL, so we need to make sure that systemd terminates the program with SIGINT
	try:
		device.send_vendor_command(USBRQ_PING, 0)
	except:
		pass
finally:
	time.sleep(1)
	if len(value := device.read()):
		print(value, flush=True)
