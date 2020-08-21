import asyncio
import threading
import serial 
import time
import ctypes

ARDUINO_BAUD_RATE = 115200

# time until setup times out in seconds
SETUP_TIMEOUT = 15
# time until read times out in seconds
SERIAL_TIMEOUT = 0.5

# time to sleep for main thread in milliseconds
INTERNAL_UPDATE_RATE_MS = 50

# Prototype data logger running on an Arduino
class ArduinoLogger:

	class SerialDataMsg(ctypes.Structure):
		_pack_ = 1
		_fields_ = [('type', ctypes.c_ubyte),
					('msgId', ctypes.c_ushort),
					('thermocoupleTemp', ctypes.c_short),
					('gasTemp', ctypes.c_short),
					('outletTemp', ctypes.c_short)]

	def __init__(self, port, update_interval_ms=1000):
		self.port = port
		self.main_thread = None
		self.thread_lock = threading.Lock()
		self.thread_started_cv = threading.Condition(self.thread_lock)
		
		self.update_interval_ms = update_interval_ms
		self.last_poll_time = time.time()
		self.polling_start_time = 0
		self.setup_start_time = 0
		
		self.thread_running = False
		self.thread_error = False
		self.thread_error_msg = ""
		
		self.setup_event = threading.Event()
		self.arduino_setup_done = False
		self.is_polling = False
		self.poll_data_queue = []
		
		self.serial_port_handle = None
		
	def start_thread(self):
		print('Starting Arduino logger on serial port {0}'.format(self.port))
		self.thread_running = False
		self.thread_error = False
		self.thread_error_msg = ""
		self.arduino_setup_done = False
		self.is_polling = False
		self.poll_data_queue = []
		self.polling_start_time = 0
		self.setup_event.clear()
		self.main_thread = threading.Thread(target=self.thread_main)
		with self.thread_started_cv:
			self.main_thread.start()
			if not self.thread_started_cv.wait(5):
				print("Failed to start the thread")
				return False
		
		return True
		
	def stop_thread(self):
		self.thread_running = False
		self.main_thread.join()
		
		self.main_thread = None
		self.serial_port_handle = None
		
	def start_polling(self):
		if self.polling_start_time == 0:
			self.polling_start_time = time.time()
		self.is_polling = True
	def stop_polling(self):
		self.is_polling = False
		
	def thread_fail(self, message):
		self.thread_error = True
		self.thread_error_msg = message
		self.thread_running = False
		
	def crc16_update(self, crc, a):
		crc ^= a
		for i in range(0, 8):
			if crc & 1:
				crc = (crc >> 1) ^ 0xA001
			else:
				crc = (crc >> 1)
		return crc
		
	# Returns thread-safe copy of queues data
	# and clears the queue
	def get_queued_data(self):
		self.thread_lock.acquire()
		data_queue_copy = self.poll_data_queue.copy()
		self.poll_data_queue = []
		self.thread_lock.release()
		return data_queue_copy
		
	def thread_main(self):
		print('poll thread enter')
		self.thread_running = True
		with self.thread_started_cv:
			self.thread_started_cv.notifyAll()
		# Attempt to open com port
		try:
			self.serial_port_handle = serial.Serial()
			self.serial_port_handle.port = self.port
			self.serial_port_handle.baudrate = ARDUINO_BAUD_RATE
			self.serial_port_handle.timeout = SERIAL_TIMEOUT
			self.serial_port_handle.setDTR(False)
			self.serial_port_handle.open()
		except serial.SerialException as e:
			self.thread_fail(e)
			return
		
		self.setup_start_time = time.time()
		data_buffer = bytearray()
		
		print('Waiting for arduino to finish setup...')
		
		while self.thread_running:
			# if Arduino has finished setup
			if self.arduino_setup_done and self.is_polling:
				if ((time.time() - self.last_poll_time) * 1000) > self.update_interval_ms:
					try:
						self.serial_port_handle.flushInput()
						self.serial_port_handle.flushOutput()
						self.serial_port_handle.write('t'.encode('utf-8'))
						# Try to read bytes
						# read struct len + checksum + ACK
						data_len = ctypes.sizeof(self.SerialDataMsg) + ctypes.sizeof(ctypes.c_ushort) + 1
						bytes_read = self.serial_port_handle.read(data_len)
						if len(bytes_read) < data_len:
							print('invalid response from arduino: {0}'.format(bytes_read))
							continue
						# check for ACK
						if bytes_read[0] != 0x06:
							print('arduino response did not begin with ACK')
							print(bytes_read)
						# read checksum
						checksum = int.from_bytes(bytes_read[1:3], byteorder="little", signed=False)
						# generate checksum of remaining data
						checksum_calced = 0
						for byte in bytes_read[3:]:
							checksum_calced = self.crc16_update(checksum_calced, byte)
						data_struct = self.SerialDataMsg.from_buffer_copy(bytes_read[3:])
						# Format data for poll data queue
						# Format:
						#	gasTemp
						#	outletTemp
						#	timestamp
						data_block = [data_struct.gasTemp / 100, data_struct.outletTemp / 100, time.time() - self.polling_start_time]
						self.thread_lock.acquire()
						self.poll_data_queue.append(data_block)
						self.thread_lock.release()
					except serial.SerialException as e:
						self.thread_fail(e)
						continue
					self.last_poll_time = time.time()
			# wait for "SETUP DONE"
			elif not self.arduino_setup_done:
				incoming_data = self.serial_port_handle.read(1)
				data_buffer.extend(incoming_data)
				#data_buffer.append(incoming_data)
				if len(data_buffer) > 10:
					if "SETUP DONE!" in data_buffer.decode():
						self.arduino_setup_done = True
						self.setup_event.set()
						print("Arduino finished setup")
						
				# Check if timed out setup
				if time.time() - self.setup_start_time > SETUP_TIMEOUT:
					self.thread_fail('Arduino failed to setup or did not respond')
					continue
			
			time.sleep(INTERNAL_UPDATE_RATE_MS / 1000)
			
		self.serial_port_handle.close()
		print('poll thread exit')