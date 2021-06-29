"""
This is free and unencumbered software released into the public domain.

Anyone is free to copy, modify, publish, use, compile, sell, or
distribute this software, either in source code form or as a compiled
binary, for any purpose, commercial or non-commercial, and by any
means.

In jurisdictions that recognize copyright laws, the author or authors
of this software dedicate any and all copyright interest in the
software to the public domain. We make this dedication for the benefit
of the public at large and to the detriment of our heirs and
successors. We intend this dedication to be an overt act of
relinquishment in perpetuity of all present and future rights to this
software under copyright law.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
OTHER DEALINGS IN THE SOFTWARE.

For more information, please refer to <https://unlicense.org>
"""

import csv
import glob
import socket
import sys
import threading
import time

import numpy as np
import pyqtgraph as pg
import pyqtgraph.exporters
import serial
from PyQt5 import uic, QtCore
from PyQt5.QtWidgets import QApplication, QMainWindow


class Window(QMainWindow):
    def __init__(self):
        super(Window, self).__init__()
        # Load GUI file
        uic.loadUi('LR4.ui', self)

        # System variables
        self.serial_port = None
        self.udp_ip = None
        self.udp_port = None
        self.udp_socket = None
        self.file_source = None
        self.file_destination = None
        self.reader_working = False
        self.first_packet_time = -1
        self.points = [[0] * 500, [0] * 500, [0] * 500, [0] * 500, [0] * 500]
        self.source_timestamp = 0
        self.channel_1 = 0
        self.channel_2 = 0
        self.channel_3 = 0
        self.channel_4 = 0
        self.csv_writer = None

        self.plot_timer = QtCore.QTimer()
        self.plot_timer.timeout.connect(self.update_plots)
        self.plot_timer.start(30)

        # Connect GUI controls
        self.btn_start.clicked.connect(self.oscilloscope_start)
        self.btn_stop.clicked.connect(self.oscilloscope_stop)
        self.btn_serial_refresh.clicked.connect(self.refresh_serial_ports)
        self.btn_save_image.clicked.connect(self.save_image)

        # Initialize pyQtGraph charts
        self.init_charts()

        # Add serial speeds
        self.init_serial_bauds()

        # Show GUI
        self.show()

        # Refresh serial ports
        self.refresh_serial_ports()

    def init_serial_bauds(self):
        """
        Adds serial speeds (baud rates) to the combo box
        :return:
        """
        self.combo_serial_speed.clear()
        self.combo_serial_speed.addItems(['9600', '110', '300', '600', '1200', '2400', '4800',
                                          '14400', '19200', '38400', '57600', '115200', '128000'])

    def refresh_serial_ports(self):
        """
        Gets list of the serial ports and adds them to the combo box
        :return:
        """
        self.combo_serial.clear()
        if sys.platform.startswith('win'):
            ports = ['COM%s' % (i + 1) for i in range(256)]
        elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
            ports = glob.glob('/dev/tty[A-Za-z]*')
        elif sys.platform.startswith('darwin'):
            ports = glob.glob('/dev/tty.*')
        else:
            raise EnvironmentError('Unsupported platform')
        for port in ports:
            try:
                s = serial.Serial(port)
                s.close()
                self.combo_serial.addItem(port)
            except (OSError, serial.SerialException):
                pass

    def oscilloscope_start(self):
        """
        Opens ports / files and starts background reading process
        :return:
        """
        if self.radio_serial.isChecked() and len(self.combo_serial.currentText()) > 0:
            # Open serial port
            print('Using serial port', self.combo_serial.currentText())
            self.serial_port = serial.Serial(self.combo_serial.currentText(),
                                             int(self.combo_serial_speed.currentText()))
            self.serial_port.close()
            self.serial_port.open()
            print('Port opened?', self.serial_port.isOpen())
            self.udp_ip = None
            self.udp_port = None
            self.file_source = None
        elif self.radio_udp.isChecked() and len(self.line_udp.text()) > 0:
            # Define UDP IP and Port
            ip_port = str(self.line_udp.text()).split(':')
            print('Using UDP port', self.line_udp.text())
            self.udp_ip = ip_port[0]
            self.udp_port = int(ip_port[1])
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.bind((self.udp_ip, self.udp_port))
            self.serial_port = None
            self.file_source = None
        elif self.radio_file.isChecked() and len(self.data_file.text()) > 0:
            # Open file
            print('Using file', self.data_file.text())
            self.file_source = open(self.data_file.text(), newline='')
            self.serial_port = None
            self.udp_ip = None
            self.udp_port = None
        else:
            # Nothing to open
            self.serial_port = None
            self.udp_ip = None
            self.udp_port = None
            self.file_source = None
            self.reader_working = False
            print('Nothing to open')

        if self.udp_ip is not None or self.serial_port is not None or self.file_source is not None:
            # If Serial or UDP port
            self.btn_start.setEnabled(False)
            self.btn_stop.setEnabled(True)
            self.reader_working = True
            self.source_timestamp = 0
            thread = threading.Thread(target=self.async_data_reader)
            thread.start()

    # noinspection PyBroadException
    def oscilloscope_stop(self):
        """
        Stops reading data and closes files and ports
        :return:
        """
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.reader_working = False
        try:
            if self.file_destination is not None:
                self.file_destination.close()
            if self.file_source is not None:
                self.file_source.close()
            if self.udp_socket is not None:
                self.udp_socket.close()
            if self.serial_port is not None:
                self.serial_port.close()
        except:
            pass

    def async_data_reader(self):
        """
        Reads data from the serial port, udp port or file
        :return:
        """
        data_buffer = [0] * 11
        data_buffer_position = 0
        data_previous = 0

        while self.reader_working:
            if self.file_source is not None:
                # Read from CSV file
                csv_reader = csv.reader(self.file_source, delimiter=',')
                for row in csv_reader:
                    if self.source_timestamp > 0:
                        time.sleep((int(row[0]) - self.source_timestamp) / 1000)
                    self.source_timestamp = int(row[0])
                    self.parse_data(int(float(row[1])), int(float(row[2])), int(float(row[3])), int(float(row[4])))
                self.reader_working = False
                print('End of CSV file')
                self.oscilloscope_stop()
                break
            else:
                # Read from other sources
                incoming_data = None
                if self.serial_port is not None and self.serial_port.isOpen():
                    incoming_data = self.serial_port.read()
                elif self.udp_ip is not None:
                    incoming_data, address = self.udp_socket.recvfrom(1024)
                    self.udp_socket.sendto(incoming_data, address)

                if incoming_data is not None and len(incoming_data) > 0:
                    for data_byte in incoming_data:
                        data_buffer[data_buffer_position] = data_byte
                        if data_buffer[data_buffer_position] == 255 and data_previous == 255:
                            data_buffer_position = 0

                            check_sum = 0
                            for i in range(0, 8):
                                check_sum ^= int(data_buffer[i] & 0xFF)

                            if check_sum == data_buffer[8]:
                                # Parse packet
                                channel_1 = (int(data_buffer[0] & 0xFF) << 8) | int(data_buffer[1] & 0xFF)
                                channel_2 = (int(data_buffer[2] & 0xFF) << 8) | int(data_buffer[3] & 0xFF)
                                channel_3 = (int(data_buffer[4] & 0xFF) << 8) | int(data_buffer[5] & 0xFF)
                                channel_4 = (int(data_buffer[6] & 0xFF) << 8) | int(data_buffer[7] & 0xFF)
                                self.parse_data(channel_1, channel_2, channel_3, channel_4)
                            else:
                                print('Wrong checksum')
                        else:
                            data_previous = data_buffer[data_buffer_position]
                            data_buffer_position += 1
                            if data_buffer_position >= 11:
                                data_buffer_position = 0

        print('Reader closed')
        self.oscilloscope_stop()

    def parse_data(self, channel_1, channel_2, channel_3, channel_4):
        """
        Filters channels, plots them on the chart and writes to the file
        :return:
        """
        # Calculate timestamp
        if self.first_packet_time < 0:
            self.first_packet_time = time.time()
        packet_time = int((time.time() - self.first_packet_time) * 1000)

        # Filter data
        if self.checkbox_filter.isChecked():
            filter_factor = self.spin_filter.value()
            self.channel_1 = self.channel_1 * filter_factor + channel_1 * (1.0 - filter_factor)
            self.channel_2 = self.channel_2 * filter_factor + channel_2 * (1.0 - filter_factor)
            self.channel_3 = self.channel_3 * filter_factor + channel_3 * (1.0 - filter_factor)
            self.channel_4 = self.channel_4 * filter_factor + channel_4 * (1.0 - filter_factor)
        else:
            self.channel_1 = channel_1
            self.channel_2 = channel_2
            self.channel_3 = channel_3
            self.channel_4 = channel_4

        # Write to file if enabled
        if self.checkbox_write_file.isChecked() and self.file_destination is not None:
            # Write to file
            self.csv_writer.writerow([packet_time, self.channel_1, self.channel_2,
                                      self.channel_3, self.channel_4])
        elif self.checkbox_write_file.isChecked() and self.file_destination is None:
            # Create file
            self.file_destination = open(self.data_file_out.text(), 'w+', newline='')
            self.csv_writer = csv.writer(self.file_destination, delimiter=',')
        elif not self.checkbox_write_file.isChecked() and self.file_destination is not None:
            # Close file
            self.file_destination.close()
            self.file_destination = None
            self.csv_writer = None

        # Display data on plot
        self.points[0] = self.points[0][1:]
        self.points[0].append(packet_time)
        self.points[1] = self.points[1][1:]
        self.points[1].append(self.channel_1)
        self.points[2] = self.points[2][1:]
        self.points[2].append(self.channel_2)
        self.points[3] = self.points[3][1:]
        self.points[3].append(self.channel_3)
        self.points[4] = self.points[4][1:]
        self.points[4].append(self.channel_4)

    def save_image(self):
        """
        Saves screenshot from the pyQtGraph
        :return:
        """
        exporter = pg.exporters.ImageExporter(self.graphWidget.plotItem)
        exporter.export(self.line_image_dir.text() + 'image.png')

    def init_charts(self):
        """
        Initializes charts
        :return:
        """
        self.graphWidget.setBackground((255, 255, 255))
        self.graphWidget.showGrid(x=True, y=True, alpha=0.7)
        self.graphWidget.setYRange(0, 400, padding=0)

    def update_plots(self):
        """
        Updates channel plots
        :return:
        """
        self.graphWidget.clear()

        # Channel 1
        amplitudes = np.array(self.points[1][-self.slider_points.value():])
        if self.checkbox_ch1_auto.isChecked():
            if np.max(amplitudes) != 0:
                amplitudes -= np.min(amplitudes)
                amplitudes = amplitudes / np.max(amplitudes) * 100
        else:
            amplitudes = amplitudes / 1000
            amplitudes *= self.slider_ampl_1.value()
        amplitudes = amplitudes - ((np.max(amplitudes) + np.min(amplitudes)) / 2) + 350
        self.graphWidget.plot(self.points[0][-self.slider_points.value():], amplitudes, pen=pg.mkPen((255, 63, 127)),
                              symbolBrush=None, symbolSize=0)

        # Channel 2
        amplitudes = np.array(self.points[2][-self.slider_points.value():])
        if self.checkbox_ch2_auto.isChecked():
            if np.max(amplitudes) != 0:
                amplitudes -= np.min(amplitudes)
                amplitudes = amplitudes / np.max(amplitudes) * 100
        else:
            amplitudes = amplitudes / 1000
            amplitudes *= self.slider_ampl_2.value()
        amplitudes = amplitudes - ((np.max(amplitudes) + np.min(amplitudes)) / 2) + 250
        self.graphWidget.plot(self.points[0][-self.slider_points.value():], amplitudes, pen=pg.mkPen((255, 200, 0)),
                              symbolBrush=None, symbolSize=0)

        # Channel 3
        amplitudes = np.array(self.points[3][-self.slider_points.value():])
        if self.checkbox_ch3_auto.isChecked():
            if np.max(amplitudes) != 0:
                amplitudes -= np.min(amplitudes)
                amplitudes = amplitudes / np.max(amplitudes) * 100
        else:
            amplitudes = amplitudes / 1000
            amplitudes *= self.slider_ampl_3.value()
        amplitudes = amplitudes - ((np.max(amplitudes) + np.min(amplitudes)) / 2) + 150
        self.graphWidget.plot(self.points[0][-self.slider_points.value():], amplitudes, pen=pg.mkPen((0, 127, 255)),
                              symbolBrush=None, symbolSize=0)

        # Channel 4
        amplitudes = np.array(self.points[4][-self.slider_points.value():])
        if self.checkbox_ch4_auto.isChecked():
            if np.max(amplitudes) != 0:
                amplitudes -= np.min(amplitudes)
                amplitudes = amplitudes / np.max(amplitudes) * 100
        else:
            amplitudes = amplitudes / 1000
            amplitudes *= self.slider_ampl_4.value()
        amplitudes = amplitudes - ((np.max(amplitudes) + np.min(amplitudes)) / 2) + 50
        self.graphWidget.plot(self.points[0][-self.slider_points.value():], amplitudes, pen=pg.mkPen((0, 255, 127)),
                              symbolBrush=None, symbolSize=0)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('fusion')
    win = Window()
    sys.exit(app.exec_())
