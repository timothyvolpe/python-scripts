import tkinter as tk
from tkinter import ttk 
import threading
import sys
import glob
import serial
import math
from arduino_proto import ArduinoLogger

import numpy as np
from matplotlib.backends.backend_tkagg import (
    FigureCanvasTkAgg, NavigationToolbar2Tk)
# Implement the default Matplotlib key bindings.
import matplotlib


POLL_INTERVAL_MAX_MS = 100000
DEFAULT_POLL_INTERVAL_MS = 1000
POLL_INTERVAL_MIN_MS = 200

# Fahrenheit
Y_AXIS_MAX_VALUE = 1000
DEFAULT_Y_AXIS_MAX = 212
DEFAULT_Y_AXIS_MIN = 50
Y_AXIS_MIN_VALUE = 32

DEFAULT_X_AXIS_MAX = 200
X_AXIS_MAX_VALUE = 1000
X_AXIS_MIN_VALUE = 5

UNIT_LOOKUP = ['', u'\N{DEGREE SIGN}' + 'F', u'\N{DEGREE SIGN}' + 'C', 'K']

class DistillogTempInterface:
	def __init__(self, parent):
		self.root = parent
		self.root.title("Distillog Temperature Reader")
		self.root.minsize(800,600)
		self.root.protocol("WM_DELETE_WINDOW", self.close)
		
		self.current_unit = 1
		
		############
		# Controls #
		############
		
		self.side_bar = tk.Frame(self.root, padx=5, pady=5)
		self.side_bar.pack(side=tk.LEFT, fill=tk.Y)
		
		self.graph_frame_parent = tk.Frame(self.root, bg='gray', relief=tk.SUNKEN, bd=2)
		self.graph_frame_parent.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
		
		self.graph_frame = tk.Frame(self.graph_frame_parent)
		self.graph_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
		
		self.status_bar = tk.Label(self.graph_frame_parent, text='Data Points: 0\t\t Start Time: 00:00:00\t Elapsed Time: 00:00:00', bd=1, relief=tk.SUNKEN, anchor=tk.W)
		self.status_bar.pack(side=tk.BOTTOM, fill=tk.X, expand=False)
		
		self.serial_options = tk.LabelFrame(self.side_bar, text="Serial Port", padx=5, pady=5)
		self.serial_options.pack(side=tk.TOP, fill=tk.X)
		
		self.serial_port_entry_var = tk.StringVar(self.root)
		self.serial_port_entry_var.set("")
		choices = {''}
		self.serial_port_entry = ttk.Combobox(self.serial_options, textvariable=self.serial_port_entry_var, state="readonly")
		self.serial_port_entry.config(width=20)
		self.serial_port_entry.pack(side=tk.TOP, fill=tk.X)
		
		self.serial_btns_frame = tk.Frame(self.serial_options)
		self.serial_btns_frame.pack(side=tk.TOP, fill=tk.X, expand=True)
		
		self.serial_connect_btn = tk.Button(self.serial_btns_frame, text="Connect", command=self.connect_serial)
		self.serial_connect_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)
		
		self.serial_refresh_btn = tk.Button(self.serial_options, text="Refresh", command=self.refresh_serial_ports)
		self.serial_refresh_btn.pack(side=tk.TOP, fill=tk.X, expand=True)
		
		self.serial_disconnect_btn = tk.Button(self.serial_btns_frame, text="Disconnect", command=self.disconnect_serial)
		self.serial_disconnect_btn.pack(side=tk.RIGHT, fill=tk.X, expand=True)
		
		self.serial_status = tk.Label(self.serial_options, text="Status: Disconnected")
		self.serial_status.pack(side=tk.BOTTOM, fill=tk.Y, expand=True)
		
		self.poll_options = tk.LabelFrame(self.side_bar, text='Polling Options', padx=5, pady=5)
		self.poll_options.pack(side=tk.TOP, fill=tk.X)
		
		self.poll_interval_label = tk.Label(self.poll_options, text='Poll Interval (ms):', anchor=tk.W)
		self.poll_interval_label.pack(side=tk.TOP, fill=tk.X, expand=True)
		
		self.poll_interval_entry_var = tk.IntVar(self.root)
		self.poll_interval_entry_var.set(DEFAULT_POLL_INTERVAL_MS)
		int_validate_cmd = (self.root.register(self.integer_entry_validate), '%s', '%P')
		
		self.poll_interval_entry = tk.Entry(self.poll_options, textvariable=self.poll_interval_entry_var, validate='key', validatecommand=int_validate_cmd)
		self.poll_interval_entry.pack(side=tk.TOP, fill=tk.X, expand=True)
		
		self.poll_unit_label = tk.Label(self.poll_options, text='Temperature Unit:', anchor=tk.W)
		self.poll_unit_label.pack(side=tk.TOP, fill=tk.X, expand=True)
		self.poll_unit_frame = tk.Frame(self.poll_options)
		self.poll_unit_frame.pack(side=tk.TOP, fill=tk.X, expand=True)
		
		self.poll_unit_var = tk.IntVar()
		self.poll_unit_var.set(self.current_unit)
		self.poll_unit_var.trace('w', self.switch_units)
		self.poll_unit_imperial = tk.Radiobutton(self.poll_unit_frame, text=[u'\N{DEGREE SIGN}','F'], value=1, variable=self.poll_unit_var)
		self.poll_unit_imperial.pack(side=tk.LEFT, fill=tk.X, expand=True)
		self.poll_unit_si = tk.Radiobutton(self.poll_unit_frame, text=[u'\N{DEGREE SIGN}','C'], value=2, variable=self.poll_unit_var)
		self.poll_unit_si.pack(side=tk.LEFT, fill=tk.X, expand=True)
		self.poll_unit_kelvin = tk.Radiobutton(self.poll_unit_frame, text='K', value=3, variable=self.poll_unit_var)
		self.poll_unit_kelvin.pack(side=tk.LEFT, fill=tk.X, expand=True)
		
		self.poll_max_y_label = tk.Label(self.poll_options, text='Y Axis Max (' + UNIT_LOOKUP[self.current_unit] + '):', anchor=tk.W)
		self.poll_max_y_label.pack(side=tk.TOP, fill=tk.X, expand=True)
		self.poll_max_y_entry_var = tk.IntVar(self.root)
		self.poll_max_y_entry_var.set(DEFAULT_Y_AXIS_MAX)
		self.poll_max_y_entry = tk.Entry(self.poll_options, textvariable=self.poll_max_y_entry_var, validate='key', validatecommand=int_validate_cmd)
		self.poll_max_y_entry.pack(side=tk.TOP, fill=tk.X, expand=True)
		
		self.poll_min_y_label = tk.Label(self.poll_options, text='Y Axis Min (' + UNIT_LOOKUP[self.current_unit] + '):', anchor=tk.W)
		self.poll_min_y_label.pack(side=tk.TOP, fill=tk.X, expand=True)
		self.poll_min_y_entry_var = tk.IntVar(self.root)
		self.poll_min_y_entry_var.set(DEFAULT_Y_AXIS_MIN)
		self.poll_min_y_entry = tk.Entry(self.poll_options, textvariable=self.poll_min_y_entry_var, validate='key', validatecommand=int_validate_cmd)
		self.poll_min_y_entry.pack(side=tk.TOP, fill=tk.X, expand=True)
		
		self.poll_max_x_label = tk.Label(self.poll_options, text='X Axis Max (s):', anchor=tk.W)
		self.poll_max_x_label.pack(side=tk.TOP, fill=tk.X, expand=True)
		self.poll_max_x_entry_var = tk.IntVar(self.root)
		self.poll_max_x_entry_var.set(DEFAULT_X_AXIS_MAX)
		self.poll_max_x_entry = tk.Entry(self.poll_options, textvariable=self.poll_max_x_entry_var, validate='key', validatecommand=int_validate_cmd)
		self.poll_max_x_entry.pack(side=tk.TOP, fill=tk.X, expand=True)
		
		self.poll_start_btn = tk.Button(self.poll_options, text='Start Polling', state='disabled', command=self.start_poll)
		self.poll_start_btn.pack(side=tk.TOP,fill=tk.X, expand=True)
		self.poll_stop_btn = tk.Button(self.poll_options, text='Stop Polling', state='disabled', command=self.stop_poll)
		self.poll_stop_btn.pack(side=tk.TOP,fill=tk.X, expand=True)
		
		self.graph_figure = matplotlib.figure.Figure(figsize=(5,4), dpi=100)
		
		self.temp_axes = self.graph_figure.add_subplot(111)
		self.temp_axes.set_title('Temperature vs. Time')
		self.temp_axes.set_xlabel('Time (s)')
		self.temp_axes.set_ylabel('Temperature (F)')
		self.temp_axes.set_ylim([DEFAULT_Y_AXIS_MIN, DEFAULT_Y_AXIS_MAX])
		self.temp_axes.set_xlim([0, X_AXIS_MIN_VALUE])
		
		# matplotlib embedded
		self.temp_graph = FigureCanvasTkAgg(self.graph_figure, master=self.graph_frame)
		self.temp_graph.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
		
		#############
		# Variables #
		#############
		
		self.serial_connected = False
		
		self.serial_ports_lock = threading.Lock()
		self.serial_ports_list = []
		self.serial_ports_list_new = False
		
		self.data_logger = None
		
		self.x_axis_max = DEFAULT_X_AXIS_MAX
		self.y_axis_max = DEFAULT_Y_AXIS_MAX
		self.y_axis_min = DEFAULT_Y_AXIS_MIN
		
		self.data_points = 0
		self.x_time = []
		self.y_gas_temp = []
		self.y_outlet_temp = []
		
		# Get serial ports
		self.refresh_serial_ports()
		self.refresh_serial_options()
		# Schedule update
		self.root.after(50, self.update)
		
	def close(self):
		self.disconnect_serial()
		self.root.destroy()
		
	def update(self, interval=50):
		# Check for serial port list update
		self.serial_ports_lock.acquire()
		if self.serial_ports_list_new:
			self.serial_ports_list_new = False
			self.serial_port_entry['value'] = self.serial_ports_list
			if self.serial_ports_list:
				self.serial_port_entry_var.set(self.serial_ports_list[0])
		self.serial_ports_lock.release()
		# if connected
		if self.data_logger:
			# Check if serial thread is okay
			if self.data_logger.thread_error:
				tk.messagebox.showerror(title="Serial Port Error",message=self.data_logger.thread_error_msg)
				self.data_logger.thread_error = False
				self.data_logger.thread_error_msg = ""
				self.disconnect_serial()
			elif not self.data_logger.main_thread.is_alive() and self.data_logger.thread_running:
				print('serial thread stopped unexpectedly')
				self.disconnect_serial()
			# check if arduino is ready
			elif self.data_logger.setup_event.isSet():
				self.data_logger.setup_event.clear()
				self.serial_status["text"] = 'Status: Ready'
				self.refresh_serial_options()
			# Check if polling
			elif self.data_logger.is_polling:
				# Get poll data queue
				poll_data = self.data_logger.get_queued_data()
				# Graph the data
				if poll_data:
					self.data_points += len(poll_data)
					self.plot_new_data(poll_data)
				
		
		self.status_bar['text']='Data Points: {0}\t\t Start Time: 00:00:00\t Elapsed Time: 00:00:00'.format(self.data_points)
		
		self.root.after(interval, self.update, interval)
		
	def plot_new_data(self, data):
		# Create data points
		for point in data:
			self.y_gas_temp.append(point[0])
			self.y_outlet_temp.append(point[1])
			self.x_time.append(point[2])
		plot_lines = self.temp_axes.get_lines()
		# Update scale
		elapsed_seconds = self.x_time[-1]
		if elapsed_seconds < self.x_axis_max:
			self.temp_axes.set_xlim([0, max(X_AXIS_MIN_VALUE, math.ceil(elapsed_seconds))])
		if plot_lines:
			plot_lines[0].set_data(self.x_time, self.y_gas_temp)
			self.temp_axes.draw_artist(plot_lines[0])
			self.temp_graph.draw()
		else:
			self.temp_axes.plot(self.x_time, self.y_gas_temp)
			self.temp_graph.draw()
		
	# Disables or enables serial options and label based on serial status
	def refresh_serial_options(self):
		if self.serial_connected:
			self.serial_connect_btn['state'] = tk.DISABLED
			self.serial_disconnect_btn['state'] = tk.NORMAL
			self.serial_refresh_btn['state'] = tk.DISABLED
			#self.serial_status["text"] = 'Status: Connected'
			self.serial_port_entry['state'] = tk.DISABLED
			
			self.poll_start_btn['state'] = tk.DISABLED
			self.poll_stop_btn['state'] = tk.DISABLED
			if self.data_logger and self.data_logger.arduino_setup_done:
					if self.data_logger.is_polling:
						self.poll_stop_btn['state'] = tk.NORMAL
					else:
						self.poll_start_btn['state'] = tk.NORMAL
						
			self.poll_unit_imperial['state'] = tk.DISABLED
			self.poll_unit_si['state'] = tk.DISABLED
			self.poll_unit_kelvin['state'] = tk.DISABLED
		else:
			self.serial_connect_btn['state'] = tk.NORMAL
			self.serial_disconnect_btn['state'] = tk.DISABLED
			self.serial_refresh_btn['state'] = tk.NORMAL
			self.serial_status['text'] = 'Status: Disconnected'
			self.serial_port_entry['state'] = 'readonly'
			self.poll_start_btn['state'] = tk.DISABLED
			self.poll_stop_btn['state'] = tk.DISABLED
			
			self.poll_unit_imperial['state'] = tk.NORMAL
			self.poll_unit_si['state'] = tk.NORMAL
			self.poll_unit_kelvin['state'] = tk.NORMAL
		
	# Credit - https://stackoverflow.com/a/14224477/953613
	def refresh_serial_ports(self):
		print("refreshing serial port list...")
		if sys.platform.startswith('win'):
			ports = ['COM%s' % (i + 1) for i in range(256)]
		elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
			# this excludes your current terminal "/dev/tty"
			ports = glob.glob('/dev/tty[A-Za-z]*')
		elif sys.platform.startswith('darwin'):
			ports = glob.glob('/dev/tty.*')
		else:
			raise EnvironmentError('Unsupported platform')
		
		def check_ports(ports):
			results = []
			for port in ports:
				try:
					s = serial.Serial(port)
					s.close()
					results.append(port)
				except (OSError, serial.SerialException):
					pass
					
			self.serial_ports_lock.acquire()
			self.serial_ports_list = results
			self.serial_ports_list_new = True
			self.serial_ports_lock.release()
		
		task = threading.Thread(target=check_ports, args=(ports,))
		task.start()
				
	def connect_serial(self):
		# Check for port
		port = self.serial_port_entry_var.get()
		if not port:
			print('No port was specified')
			return
		if self.data_logger:
			print('Already connected')
			return
		# Cleanup old
		self.data_points = 0
		self.x_time = []
		self.y_gas_temp = []
		self.y_outlet_temp = []
		# Create new data logger
		self.data_logger = ArduinoLogger(port)
		self.data_logger.start_thread()
	
		self.serial_connected = True
		
		self.refresh_serial_options()
		self.serial_status["text"] = 'Status: Waiting...'
		
	def disconnect_serial(self):
		if self.data_logger:
			self.data_logger.stop_thread()
		self.data_logger = None
		self.serial_connected = False
		
		self.refresh_serial_options()
		
	def integer_entry_validate(self, prior, check_str):
		if not check_str:
			return True
		try:
			check_int = float(check_str)
		except ValueError:
			return False
		return True
		
	def switch_units(self, n, m, x):
		if self.current_unit == self.poll_unit_var.get():
			return
		print('Switching from {0} to {1}'.format(UNIT_LOOKUP[self.current_unit], UNIT_LOOKUP[self.poll_unit_var.get()]))
		old_index = self.current_unit
		self.current_unit = self.poll_unit_var.get()
		
		self.poll_max_y_label['text'] = 'Y Axis Max (' + UNIT_LOOKUP[self.current_unit] + '):'
		self.poll_min_y_label['text'] = 'Y Axis Min (' + UNIT_LOOKUP[self.current_unit] + '):'
		
		self.poll_min_y_entry_var.set(self.unit_convert(self.poll_min_y_entry_var.get(), old_index, self.current_unit))
		self.poll_max_y_entry_var.set(self.unit_convert(self.poll_max_y_entry_var.get(), old_index, self.current_unit))
		
	def unit_convert(self, temp, old_index, new_index):
		# F to C
		if old_index == 1 and new_index == 2:
			return (temp - 32) * 5/9
		# F to K
		elif old_index == 1 and new_index == 3:
			return (temp - 32) * 5/9 + 273.15
		# C to F
		elif old_index == 2 and new_index == 1:
			return temp * 9/5 + 32
		# C to K
		elif old_index == 2 and new_index == 3:
			return temp + 273.15
		# K to F
		elif old_index == 3 and new_index == 1:
			return (temp - 273.15) * 9/5 + 32
		# K to C
		elif old_index == 3 and new_index == 2:
			return temp - 273.15
		else:
			print('invalid conversion indices ({0} and {1})'.format(old_index, new_index))
			return temp
		
	def start_poll(self):
		if self.data_logger:
			if self.data_logger.arduino_setup_done:
				# clamp and set update interval
				try:
					self.data_logger.update_interval_ms = max(POLL_INTERVAL_MIN_MS, min(self.poll_interval_entry_var.get(), POLL_INTERVAL_MAX_MS))
				except tk.TclError:
					self.data_logger.update_interval_ms = DEFAULT_POLL_INTERVAL_MS
				self.poll_interval_entry_var.set(self.data_logger.update_interval_ms)
				# clamp and set axis range
				try:
					y_axis_max = max(Y_AXIS_MIN_VALUE, min(self.poll_max_y_entry_var.get(), Y_AXIS_MAX_VALUE))
				except tk.TclError:
					y_axis_max = DEFAULT_Y_AXIS_MAX
				try:
					y_axis_min = max(Y_AXIS_MIN_VALUE, min(self.poll_min_y_entry_var.get(), Y_AXIS_MAX_VALUE))
				except tk.TclError:
					y_axis_min = DEFAULT_Y_AXIS_MIN
				if y_axis_min >= y_axis_max:
					y_axis_max = DEFAULT_Y_AXIS_MAX
					y_axis_min = DEFAULT_Y_AXIS_MIN
				self.poll_max_y_entry_var.set(y_axis_max)
				self.poll_min_y_entry_var.set(y_axis_min)
				
				try:
					x_axis_max = max(X_AXIS_MIN_VALUE, min(self.poll_max_x_entry_var.get(), X_AXIS_MAX_VALUE))
				except tk.TclError:
					x_axis_max = DEFAULT_X_AXIS_MAX
				self.poll_max_x_entry_var.set(x_axis_max)
				
				self.x_axis_max = x_axis_max
				self.y_axis_max = y_axis_max
				self.y_axis_min = y_axis_min
				
				self.temp_axes.set_ylim([y_axis_min, y_axis_max])
				self.temp_axes.set_xlim([0, X_AXIS_MIN_VALUE])
				self.temp_graph.draw()
				
				self.data_logger.start_polling()
			else:
				print('arduino setup not finished')
		else:
			print('serial not connected')
		self.refresh_serial_options()
	def stop_poll(self):
		if self.data_logger:
			self.data_logger.stop_polling()
		else:
			print('serial not connected')
		self.refresh_serial_options()


def open_interface():
	root = tk.Tk()
	interface = DistillogTempInterface(root)
	root.mainloop()

if __name__ == "__main__":
	open_interface()