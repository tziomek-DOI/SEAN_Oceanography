# v0.6.0
# Added an app menu bar with the following features:
#   File -> Exit
#   Settings -> Config file - used to edit the config file (in future version)
#   Settings -> Show GPS errors - allows user to toggle on/off popup messages, in case GPS goes down.
#   Settings -> Refresh Styles - allows user to tweak styles (especially colors) and apply without closing the app.
#   GPS -> Connect (another place to connect to GPS... original button still in place for now)
#   GPS -> Refresh COM Ports - Refreshes the dropdown list of COM ports in case USB is plugged in while app is running.
#   Help -> About (version number only, currently)
# Added a config file with various settings that are user-configurable.
# Changed timestamp in output CSV to UTC time.
# Added various Q*Validators to the fields for additional QA.
# Configured to allow for manual entry of lat/long if GPS is not enabled.
# Added tooltips to the fields.
# Clear the Station group fields upon successful submission, and move focus to Cast field.
# Added descriptive text for the COM port dropdown items.
# Added status bar at bottom of window.
# - Moved live GPS readings to status bar.
# - Moved some informational messaging from popups to status bar.
#
# v0.5.0
# Renamed the app to 'oc_station_metadata_form.py'.
# Added file '__version__.py' to track version number.
# Added file '__init__.py' (indicates 'this folder is a package' for now; could be more useful later.
#
# v0.4
# Attempt to add some validation UI indicators, such as, red asterisks for fields which are required and/or have invalid input.
#
# v0.3c
# Adds a checkbox between the two left-pane groups of widgets, allowing user to toggle locking of the "survey" widgets.
#
# v0.3b
# Implements a QThread-based GPS solution, instead of the QTimer.
# This would work best if we want to add a map (such as, to replace SeaLog).
#
from version import __version__

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'libs'))
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFormLayout, QVBoxLayout, QHBoxLayout, QLineEdit, QCheckBox,
    QComboBox, QTextEdit, QPushButton, QLabel, QSplitter, QMessageBox, QGroupBox, QFrame
)

# Added QThread and pyqtSignal to implement the threaded GPS polling.
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QDoubleValidator, QIntValidator, QAction
#import ctypes
#from ctypes import wintypes
import time
from datetime import datetime, UTC
import csv
from libs.serial import Serial, SerialException  # Assuming your libs/serial for GPS connection
from libs.serial.tools import list_ports # This will feed a dropdown with available COM ports/devices

# This is used for the "Comments" box. The default behavior when hitting the TAB key from within
# the Comments TextEdit box is to actually make a TAB (indent) character.
# This class overrides that behavior so that hitting TAB will tab out of the Comments box,
# and moves to the next widget (currently, the Submit button).
class CustomTextEdit(QTextEdit):
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Tab:
            self.parent().focusNextChild()  # Move to next widget
        else:
            super().keyPressEvent(event)  # Handle other keys normally

# ChatGPT offered up this class and related code.
# Instead of using the QTimer for polling GPS, this implements running a loop reading the serial port.
# Whenever valid NMEA arrives, it emits a QT signal.
# It should stop gracefully when requested.
# This version replaces v0.3a, and should update the gps_label with the coords (it also does course/speed, but we might not use that).
class GPSWorker(QThread):
    position_update = pyqtSignal(float, float, float, float)  
    error = pyqtSignal(str)

    def __init__(self, port, baudrate=4800, parent=None):
        super().__init__(parent)
        self.port = port
        self.baudrate = baudrate
        self._running = True

    # def run(self):
        # try:
            # ser = Serial(self.port, self.baudrate, timeout=1)
        # except SerialException as e:
            # self.error.emit(f"Failed to open GPS port: {e}")
            # return

        # This works, but we replaced it with a version (below) that does a handshake timeout,
        # in the event something like, incorrect COM port was selected.
        # while self._running:
            # try:
                # line = ser.readline().decode(errors="ignore").strip()
                # if line.startswith("$GPRMC"):
                    # parsed = self.parse_gprmc(line)
                    # if parsed:
                        # lat, lon, speed, course = parsed
                        # self.position_update.emit(lat, lon, speed, course)
                        # self.current_lat = lat
                        # self.current_lon = lon
            # except SerialException as e:
                # self.error.emit(f"GPS read error: {e}")
                # break

        # ser.close()
        
    def run(self):
        ser = None
        try:
            ser = Serial(self.port, self.baudrate, timeout=1)
        except SerialException as e:
            self.error.emit(f"Failed to open GPS port: {e}")
            # 2026-03-05:
            # Commented out return so we can manually enter GPS coords from another source.
            # (otherwise, code will not allow form to be submitted)
            # return

        # Handshake timeout (wait for valid NMEA sentence)
        start_time = time.time()
        got_fix = False

        while self._running:
            try:
                line = ser.readline().decode(errors="ignore").strip()

                if line.startswith("$GPRMC"):
                    parsed = self.parse_gprmc(line)
                    if parsed:
                        lat, lon, speed, course = parsed
                        self.position_update.emit(lat, lon, speed, course)
                        self.current_lat = lat
                        self.current_lon = lon
                        got_fix = True
                        break  # handshake succeeded

            except SerialException as e:
                self.error.emit(f"GPS read error: {e}")
                ser.close()
                # 2026-03-05:
                # Commented out return so we can manually enter GPS coords from another source.
                # (otherwise, code will not allow form to be submitted)
                #return

            # Timeout if no valid data
            if not got_fix and (time.time() - start_time > 5):
                self.error.emit("No valid GPS data received (timeout). Check COM port.")
                ser.close()
                return

        # Main loop after handshake
        while self._running and got_fix:
            try:
                line = ser.readline().decode(errors="ignore").strip()
                if line.startswith("$GPRMC"):
                    parsed = self.parse_gprmc(line)
                    if parsed:
                        lat, lon, speed, course = parsed
                        self.position_update.emit(lat, lon, speed, course)
                        self.current_lat = lat
                        self.current_lon = lon
            except SerialException as e:
                self.error.emit(f"GPS read error: {e}")
                break

        ser.close()
        
    def stop(self):
        self._running = False
        self.wait()

    def parse_gprmc(self, sentence):
        try:
            parts = sentence.split(",")
            if parts[2] != "A":  # A = Active, V = Void (invalid)
                return None

            # Latitude
            raw_lat = parts[3]  # e.g. 4807.038
            lat_dir = parts[4]  # N/S
            lat = float(raw_lat[:2]) + float(raw_lat[2:]) / 60.0
            if lat_dir == "S":
                lat = -lat

            # Longitude
            raw_lon = parts[5]  # e.g. 01131.000
            lon_dir = parts[6]  # E/W
            lon = float(raw_lon[:3]) + float(raw_lon[3:]) / 60.0
            if lon_dir == "W":
                lon = -lon

            # Speed (knots → km/h if needed)
            speed = float(parts[7]) if parts[7] else 0.0
            # Course over ground
            course = float(parts[8]) if parts[8] else 0.0

            return lat, lon, speed, course
        except Exception:
            return None

    def get_latest_position(self):
        return self.current_lat, self.current_lon

# This class defines the overall application structure, particularly the UI.
class GPSApp(QMainWindow):
    def __init__(self):
        super().__init__()

        # Load the config CSV file:
        self.config = {} # will store key/value pairs
        self.statusBar().showMessage("Loading config file...")
        self.load_config()
        self.statusBar().showMessage("Config file loaded.", 5000)

        # Serial connection
        self.ser = None  # Initialize serial port as None
        self.current_lat = None
        self.current_lon = None

        # Window size and title
        self.setWindowTitle("SEAN Oceanography Station Metadata")
        self.resize(1000, 700)

        # Styling
        self.statusBar().showMessage("Loading stylesheet file...")
        self.load_stylesheet()
        self.statusBar().showMessage("Stylesheet file loaded.", 3000)

        self.com_combo = QComboBox()
        #for p in list_ports.comports():
        #    self.com_combo.addItem(p.device, p) # device string, plus full info (if needed)
        self.gps_refresh_ports()

        self.connect_btn = QPushButton("Connect GPS")
        self.connect_btn.clicked.connect(self.connect_gps)
        self.gps_label = QLabel("GPS: Not connected")
        self.statusBar().addPermanentWidget(self.gps_label) # status bar will always be connected to GPS messages

        self.cruise_edit = QLineEdit()
        self.cruise_max_len = self.config.get('cruise_max_length', 20)
        self.cruise_edit.setMaxLength(self.cruise_max_len)
        self.vessel_edit = QLineEdit()
        self.vessel_edit.setMaxLength(20)
        self.observer_edit = QLineEdit()
        self.observer_max_len = self.config.get('observer_max_length', 100)
        self.observer_edit.setMaxLength(self.observer_max_len)
        self.ctd_combo = QComboBox()
        self.ctd_combo.addItems(["7", "8"])  # Replace with your actual CTD items
        self.dump_edit = QLineEdit()
        self.dump_edit.setInputMask("0000")
        self.dump_edit.setToolTip("Enter 4-digit dump value, using leading zero (e.g., 0135).")

        cast_validator = QIntValidator(0, 199)
        self.cast_edit = QLineEdit()
        self.cast_edit.setValidator(cast_validator)
        self.cast_edit.setToolTip("Enter value between 0-1XX for cast number.")
        self.station_combo = QComboBox()
        self.station_combo.addItems(["{:02d}".format(i) for i in range(1, 25)])  # Populates dropdown with 01-24

        depth_validator = QIntValidator(1, 999)
        self.fathometer_edit = QLineEdit()
        self.fathometer_edit.setValidator(depth_validator)
        self.fathometer_edit.setToolTip("Enter value between 1-999 for fathometer depth, in meters (m).")
        self.target_edit = QLineEdit()
        self.target_edit.setValidator(depth_validator)
        self.target_edit.setToolTip("Enter value between 1-999 for target depth, in meters (m).")
        self.latitude_edit = QLineEdit()
        self.latitude_min = self.config.get('latitude_min', 58.0)
        self.latitude_max = self.config.get('latitude_max', 60.0)
        self.latitude_precision = self.config.get('latitude_decimal_places', 6)
        lat_validator = QDoubleValidator(self.latitude_min, self.latitude_max, self.latitude_precision)
        lat_validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.latitude_edit.setValidator(lat_validator)
        self.latitude_edit.setToolTip("Enter latitude in decimal degrees (e.g., 58.3019)")
        #self.latitude_help_btn = QPushButton("ⓘ")
        #self.latitude_help_btn.setFixedWidth(self.help_btn_size)
        #self.latitude_help_btn.setFixedSize(10,10)
        #self.latitude_help_btn.setProperty("help_text", "Enter latitude in decimal degrees.\nExample: 58.3019")
        #self.latitude_help_btn.clicked.connect(self.show_widget_help)
        #self.latitude_help_btn = self.create_help_button("Enter latitude in decimal degrees.\nExample: 58.3019")
        self.longitude_edit = QLineEdit()
        self.longitude_min = self.config.get('longitude_min', -136.0)
        self.longitude_max = self.config.get('longitude_max', -135.0)
        self.longitude_precision = self.config.get('longitude_decimal_places', 6)
        lon_validator = QDoubleValidator(self.longitude_min, self.longitude_max, self.longitude_precision)
        lon_validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.longitude_edit.setToolTip("Enter longitude in decimal degrees (e.g., -135.3020)")
        self.comments_edit = CustomTextEdit()
        self.comments_edit.setMaximumHeight(100)
        self.submit_btn = QPushButton("Submit")
        self.submit_btn.clicked.connect(self.submit)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)

        # Left pane: Form
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(10, 10, 10, 10)

        # COM Port and Connect button, now positioned on same row.
        form_top = QFormLayout()
        #form_top.addRow("COM Port:", self.com_combo)
        connect_hbox = QHBoxLayout()
        #connect_hbox.addStretch()
        connect_hbox.addWidget(self.com_combo)
        connect_hbox.addWidget(self.connect_btn)
        #connect_hbox.addStretch()
        self.connect_btn.setFixedWidth(150)  # Fixed width to prevent stretching
        form_top.addRow("COM Port:", connect_hbox)

        # Grok removed the .addRow for gps_label. See if this works?
        # It displays, but positioned to right of button, not good.
        #form_top.addRow(self.gps_label)
        #connect_hbox.addWidget(self.gps_label)
        
        # Removed this, and put this info in the bottom status bar instead...
        #form_top.addRow("", connect_hbox)
        # form_top.addRow("GPS Status: ", self.gps_label)
        
        left_layout.addLayout(form_top)

        # Cruise details section
        cruise_group = QGroupBox("Cruise details")
        cruise_form = QFormLayout()
        cruise_form.addRow("Cruise:", self.cruise_edit)
        cruise_form.addRow("Vessel:", self.vessel_edit)
        cruise_form.addRow("Observer:", self.observer_edit)
        cruise_form.addRow("CTD#:", self.ctd_combo)
        cruise_form.addRow("Dump#:", self.dump_edit)
        cruise_group.setLayout(cruise_form)
        left_layout.addWidget(cruise_group)

        # Checkbox that toggles locking of the Cruise details section above:
        self.lock_cruise_chk = QCheckBox("Lock Cruise Details")
        self.lock_cruise_chk.stateChanged.connect(self.toggle_cruise_lock)
        left_layout.addWidget(self.lock_cruise_chk)
        
        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        left_layout.addWidget(separator)

        # Station Survey section
        self.station_group = QGroupBox("Station Survey")
        station_form = QFormLayout()
        #station_form.addRow("Dump#:", self.dump_edit)
        station_form.addRow("Cast#:", self.cast_edit)
        station_form.addRow("Station:", self.station_combo)
        station_form.addRow("Fathometer Depth (m):", self.fathometer_edit)
        station_form.addRow("Target Depth (m):", self.target_edit)

        # latitude row:
        station_form.addRow("Latitude (dd):", self.latitude_edit)
        #station_form.addWidget(self.latitude_help_btn)
        #lat_row = QHBoxLayout()
        #lat_row.setContentsMargins(0,0,0,0)
        #lat_row.setSpacing(2) # tiny gap between line edit and button
        #lat_row.addWidget(self.latitude_edit) # should stretch to fit the row
        #lat_row.addWidget(self.latitude_help_btn) # should stay fixed
        #station_form.addRow("Latitude (dd):", lat_row)

        station_form.addRow("Longitude (dd):", self.longitude_edit)
        station_form.addRow("Comments:", self.comments_edit)
        self.station_group.setLayout(station_form)
        left_layout.addWidget(self.station_group)

        # Submit button
        submit_hbox = QHBoxLayout()
        submit_hbox.addStretch()
        submit_hbox.addWidget(self.submit_btn)
        submit_hbox.addStretch()
        self.submit_btn.setFixedWidth(150)  # Fixed width to prevent stretching
        left_layout.addLayout(submit_hbox)

        left_layout.addStretch()  # Push content up and allow scaling

        # Right pane: Log
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(10, 10, 10, 10)
        right_layout.addWidget(self.log_text)

        # Splitter
        splitter = QSplitter()
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([500, 500])  # Equal split for left and right panes

        # Set central widget
        self.setCentralWidget(splitter)

        # Create a Menu Bar:
        self.create_menubar()

        # Timer for polling GPS
        # self.timer = QTimer()
        # self.timer.timeout.connect(self.poll_gps)
        # self.timer.start(10000)  # Poll every second

    # Menu Bar:
    def create_menubar(self):
        menubar = self.menuBar()
        separator_str = "-----"
        gps_errors_str = "Show GPS errors"

        # Define the menu structure as a nested dictionary:
        menu_def = {
            "&File": {
                "E&xit": self.close
            },
            "&Settings": {
                "&Config File": self.show_config,
                f"{gps_errors_str}": self.toggle_gps_errors,
                "Refresh S&tyles": self.load_stylesheet
            },
            "&GPS": {
                "Connect": self.connect_gps,
                "Disconnect": self.gps_disconnect,
                f"{separator_str}": None, # separator
                "&Refresh COM Ports": self.gps_refresh_ports
            },
            "&Help": {
                "&About": self.show_about
            }
        }

        for menu_name, actions in menu_def.items():
            menu = menubar.addMenu(menu_name)

            for action_name, callback in actions.items():
                if action_name == separator_str:
                    menu.addSeparator()
                    continue
                elif action_name == f"{gps_errors_str}":
                    self.toggle_gps_errors_action = QAction(gps_errors_str, self)
                    self.toggle_gps_errors_action.setCheckable(True)
                    self.toggle_gps_errors_action.setChecked(True) # default state
                    self.toggle_gps_errors_action.toggled.connect(self.toggle_gps_errors)
                    menu.addAction(self.toggle_gps_errors_action)
                    continue
                menu_action = QAction(action_name, self)
                if callback: # only connect if there is a function
                    menu_action.triggered.connect(callback)
                menu.addAction(menu_action)

        # The original, hacky version:
        # # File menu
        # file_menu = menubar.addMenu("File")
        # exit_action = QAction("Exit", self)
        # exit_action.triggered.connect(self.close) # closes the app
        # file_menu.addAction(exit_action)
        #
        # # Settings menu
        # settings_menu = menubar.addMenu("Settings")
        # config_action = QAction("Config", self)
        # config_action.triggered.connect(self.show_config) # calls a sub function
        # settings_menu.addAction(config_action)
        #
        # # GPS sub-menu
        # gps_menu = menubar.addMenu("GPS")
        # connect_action = QAction("Connect GPS", self)
        # connect_action.triggered.connect(self.gps_connect)
        # disconnect_action = QAction("Disconnect GPS", self)
        # disconnect_action.triggered.connect(self.gps_disconnect)
        # refresh_ports_action = QAction("Refresh COM Ports", self)
        # refresh_ports_action.triggered.connect(self.refresh_com_ports)
        #
        # gps_menu.addAction(connect_action)
        # gps_menu.addAction(disconnect_action)
        # gps_menu.addSeparator()
        # gps_menu.addAction(refresh_ports_action)
        #
        # # Help menu
        # help_menu = menubar.addMenu("Help")
        # about_action = QAction("About", self)
        # about_action.triggered.connect(self.show_about)
        # help_menu.addAction(about_action)

    # This should allow the user to modify the styles (colors, fonts),
    # and then reload without restarting the app.
    def load_stylesheet(self):
        ss = "stylesheet_minimal.qss"
        try:
            with open(ss, 'r') as file:
                self.setStyleSheet(file.read())
        except FileNotFoundError:
            print(f"Warning: stylesheet '{ss}' not found, using default styling.")
            QMessageBox.warning(self, "Stylesheet error", f"Failed to load styles.\nCheck app directory for file '{ss}'.")

            # Default styling:
            self.setStyleSheet("""
                QWidget { font-family: Arial; font-size: 12px; }
                QLineEdit, QComboBox, QTextEdit { border: 1px solid #ccc; padding: 5px; }
                QPushButton { background-color: #f0f0f0; border: 1px solid #ccc; padding: 5px; }
            """)

    # Check box functionality to toggle RO/RW of cruise details widgets.
    #def toggle_cruise_lock(self, state):
    def toggle_cruise_lock(self, _):
        
        is_locked = self.lock_cruise_chk.isChecked()
        print("Toggle cruise lock: ", is_locked) # debug
        
        self.cruise_edit.setReadOnly(is_locked)
        self.vessel_edit.setReadOnly(is_locked)
        self.observer_edit.setReadOnly(is_locked)
        self.ctd_combo.setEnabled(not is_locked)
        self.dump_edit.setReadOnly(is_locked)

    # ChatGPT offered this set of functions which are used to implement the QThread-based GPS functionality:
    def connect_gps(self):
        self.gps_label.setText("Connecting to GPS...")
        # change to read the dropdown:
        #port = self.com_combo.currentText()
        port = self.com_combo.currentData() # should return just COMx, without additional text.
        
        self.gps_worker = GPSWorker(port)
        # v0.3a:
        #self.gps_worker.data_received.connect(self.on_gps_data)
        # v0.3b: updates the label with the data:
        self.gps_worker.position_update.connect(self.on_gps_update)
        self.gps_worker.error.connect(self.on_gps_error)
        self.gps_worker.start()

    def gps_refresh_ports(self):
        try:
            #current_port = self.com_combo.currentText()
            self.com_combo.clear()

            for p in list_ports.comports():
                #display_text = f"{p.device}: {p.description}"
                display_text = p.description
                self.com_combo.addItem(display_text, p.device) # device string, plus full info (if needed)
                # Try to keep the selected port
                #if current_port == p.device:
                #    self.com_combo.setCurrentText(current_port)

            #QMessageBox.information(self, "COM Ports", "COM Ports list has been updated.")
            self.statusBar().showMessage("COM Ports list has been updated.", 4000)
        except:
            QMessageBox.warning(self, "COM Ports", "Failed to refresh the COM Ports.\nTry restarting the app.")

    # Used in v0.3b. Modify the output string as desired.
    # We should add a checkbox or menu option to toggle on/off course/speed?
    def on_gps_update(self, lat, lon, speed, course):
        self.gps_label.setText(
            #f"Lat: {lat:.6f}, Lon: {lon:.6f}"
            f"Lat: {lat:.6f}, Lon: {lon:.6f}, Speed: {speed:.1f} kn, Course: {course:.1f}° "
        )
        # Silly issue with this: When testing
        #self.latitude_edit.setText(f"{lat:.6f}")
        #self.longitude_edit.setText(f"{lon:.6f}")

    def on_gps_data(self, line):
        if line.startswith("$GP"):  # NMEA detected
            self.gps_label.setText("Connected...acquiring coordinates...")
            # Later: parse GPGGA / GPRMC here and update map with coordinates

    def on_gps_error(self, msg):
        QMessageBox.critical(self, "GPS Error", msg)
        self.gps_label.setText("No GPS available on selected COM port.")
        self.gps_worker = None

    def closeEvent(self, event):
        if hasattr(self, "gps_worker") and self.gps_worker:
            self.gps_worker.stop()
        super().closeEvent(event)
    
    # Original app version of poll_gps.
    # def poll_gps(self):
        # if self.ser:
            # try:
                # data = self.ser.read(1024)
                # if data:
                    # lat, lon = self.parse_nmea(data)
                    # if lat is not None and lon is not None:
                        # self.current_lat = lat
                        # self.current_lon = lon
                        # self.gps_label.setText(f"GPS: {lat:.6f}, {lon:.6f}")
            # except Exception as e:
                # self.log_text.append(f"Error reading GPS: {str(e)}")
                # self.gps_label.setText(f"Error reading GPS: {str(e)}")

    # This function was from the original version of the app.
	# It is called by poll_gps.
    def parse_nmea(self, data):
        lines = data.decode('ascii', errors='ignore').splitlines()
        for line in lines:
            if line.startswith('$GPGGA'):
                fields = line.split(',')
                if len(fields) >= 6 and fields[2] and fields[4]:
                    try:
                        lat = float(fields[2])
                        lat_dir = fields[3]
                        lon = float(fields[4])
                        lon_dir = fields[5]
                        lat_deg = int(lat / 100)
                        lat_min = lat % 100
                        lat = lat_deg + lat_min / 60
                        if lat_dir == 'S':
                            lat = -lat
                        lon_deg = int(lon / 100)
                        lon_min = lon % 100
                        lon = lon_deg + lon_min / 60
                        if lon_dir == 'W':
                            lon = -lon
                        return lat, lon
                    except ValueError:
                        pass
        return None, None

    # This submit function came from the original version of the app,
	# and includes QA for data entry.
    def submit(self):
        #if self.gps_worker is None:
        #if hasattr(self, "gps_worker") and self.gps_worker is None:
        if not hasattr(self, "gps_worker") or self.gps_worker is None:
            if self.toggle_gps_errors_action.isChecked():
                msg = "GPS not connected."
                QMessageBox.warning(self, "GPS", msg)
                self.gps_label.setText(msg)
            # 2026-03-05:
            # Commented out return so the form can still be submitted even with no GPS.
            # User can enter GPS in the fields manually.
            #return

        # Force a read from the GPS device:
        # Note: On 2026-03-05, I began the change which allows the user to submit data even if
        # the USB GPS is not functioning or connected.
        # When the Submit button is clicked, and the USB GPS is not available, the gps_worker
        # here will likely be 'None'.
        # Here we use hints since we want these ultimately as float type:
        lat: float | None = None
        lon: float | None = None

        #if self.gps_worker is not None:
        if hasattr(self, "gps_worker") and self.gps_worker:
            lat, lon = self.gps_worker.get_latest_position()
        
        #if self.current_lat is None or self.current_lon is None:
        #if lat is None or lon is None:
        if None in (lat, lon): # this is more, 'Pythonic' syntax apparently...
            #if self.show_gps_errors:
            if self.toggle_gps_errors_action.isChecked():
                msg = "No GPS data available"
                QMessageBox.warning(self, "GPS", msg)
                self.gps_label.setText(msg)
                # 2026-03-05:
                # Commented out return so the form can still be submitted even with no GPS.
                # User can enter GPS in the fields manually.
                #return
        else: # added 2026-03-05 with commenting of the return statement in the 'if' block.
            self.current_lat = lat
            self.current_lon = lon
            # This updates the lat/long text fields from the GPS so that everything passes final validation:
            self.latitude_edit.setText(f"{lat:0.6f}")
            self.longitude_edit.setText(f"{lon:0.6f}")

        cruise = self.cruise_edit.text().strip()
        vessel = self.vessel_edit.text().strip()
        observer = self.observer_edit.text().strip()
        ctd = self.ctd_combo.currentText()
        dump_str = self.dump_edit.text().strip()
        cast_str = self.cast_edit.text().strip()
        station = self.station_combo.currentText()
        fathometer_str = self.fathometer_edit.text().strip()
        target_str = self.target_edit.text().strip()
        comments = self.comments_edit.toPlainText().strip()
        # 2026-03-05:
        # populate the lat and long variables from the form fields.
        # These will either contain the built-in GPS data, or the user-entered data if no GPS:
        latitude_str = self.latitude_edit.text().strip()
        longitude_str = self.longitude_edit.text().strip()

        # Validate required fields
        required_fields = {
            "Cruise": cruise,
            "Vessel": vessel,
            "Observer": observer,
            "CTD#": ctd,
            "Dump#": dump_str,
            "Cast#": cast_str,
            "Station": station,
            "Fathometer Depth": fathometer_str,
            "Target Depth": target_str,
            "Latitude": latitude_str,
            "Longitude": longitude_str
        }
        for name, value in required_fields.items():
            if not value:
                QMessageBox.warning(self, "Error", f"{name} is required")
                return

        # Validate integers and max lengths, with per-field messages
        # ChatGPT version should give better feedback.
        errors = []

        # Reset all invalid UI indicators first.
        for w in [self.cruise_edit, self.vessel_edit, self.observer_edit, self.dump_edit, self.cast_edit,
                  self.fathometer_edit, self.target_edit, self.comments_edit, self.latitude_edit, self.longitude_edit]:
            clear_invalid(w)
    
        # --- Cruise ---
        if not (1 < len(cruise) <= 30):
            errors.append("Cruise must be 1-30 characters.")
            mark_invalid(self.cruise_edit)
            
        # --- Vessel ---
        if not (1 < len(vessel) <= 20):
            errors.append("Vessel must be 1-20 characters.")
            mark_invalid(self.vessel_edit)
            
        # --- Observer ---
        if not (1 < len(observer) <= self.observer_max_len):
            errors.append(f"Observer must be 1-{self.observer_max_len} characters.")
            mark_invalid(self.observer_edit)
            self.observer_edit.setFocus()
            
        # --- Dump ---
        if not dump_str.isdigit() or len(dump_str) != 4:
            errors.append("Dump must be 4 integers (pad with leading 0, such as '0334').")
            mark_invalid(self.dump_edit)

        # --- Cast ---
        if not cast_str.isdigit() or not (1 <= len(cast_str) <= 3):
            errors.append("Cast must be numeric, between 1 to 3 digits.")
            mark_invalid(self.cast_edit)
            self.cast_edit.setFocus()

        # --- Fathometer depth ---
        if not fathometer_str.isdigit() or not (1 <= len(fathometer_str) <= 3):
            errors.append("Fathometer depth must be numeric, between 1 to 3 digits.")
            mark_invalid(self.fathometer_edit)
            self.fathometer_edit.setFocus()

        # --- Target depth ---
        if not target_str.isdigit() or not (1 <= len(target_str) <= 3):
            errors.append("Target depth must be numeric, between 1 to 3 digits.")
            mark_invalid(self.target_edit)
            self.target_edit.setFocus()

        # --- Comments ---
        if len(comments) > 1000:
            errors.append("Comments must be 1000 characters or less.")
            mark_invalid(self.comments_edit)
            self.comments_edit.setFocus()

        # --- Latitude ---
        latitude = None
        try:
            latitude = float(latitude_str)
            if not (self.latitude_min <= latitude <= self.latitude_max):
                raise ValueError
        except ValueError:
            errors.append(f"Latitude must be a decimal value, between {self.latitude_min} and {self.latitude_max}.")
            mark_invalid(self.latitude_edit)
            self.latitude_edit.setFocus()

        # --- Longitude ---
        longitude = None
        try:
            longitude = float(longitude_str)
            if not (self.longitude_min <= longitude <= self.longitude_max):
                raise ValueError
        except ValueError:
            errors.append(f"Longitude must be a decimal value, between {self.longitude_min} and {self.longitude_max}.")
            mark_invalid(self.longitude_edit)
            self.longitude_edit.setFocus()

        # If any errors, show them all at once
        if errors:
            QMessageBox.warning(
                self,
                "Input Error",
                "\n".join(errors)
            )
            return

        # If no errors, safe to convert to int
        dump = int(dump_str)
        cast = int(cast_str)
        fathometer = int(fathometer_str)
        target = int(target_str)

        # Do we want UTC time instead?? YES per CMurdoch.
        #timestamp = datetime.now().isoformat()
        #timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S") # local
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%SZ")

        dump_padded = f"{dump:04d}"
        cast_padded = f"{cast:03d}"

        # We do not need to escape the Comments field in the above manner.
        row = [
            # timestamp, cruise, vessel, observer, ctd, dump_padded, cast_padded, station,
            # str(fathometer), str(target), comments.replace('\n', '\\n'), f"{self.current_lat:.6f}", f"{self.current_lon:.6f}"
            # timestamp, cruise, vessel, observer, ctd, dump_padded, cast_padded, station,
            # str(fathometer), str(target), f"{longitude:.6f}", f"{latitude:.6f}", comments.replace('\n', '\\n')
            # Removed the string casting so we can double-quote only 'strings' in the CSV:
            timestamp, cruise, vessel, observer, ctd, dump_padded, cast_padded, station, fathometer, target,
            round(latitude,self.latitude_precision), round(longitude,self.longitude_precision), comments.replace('\n', '\\n')
        ]
        
        # Let us customize the output on the right-side pane to make it more readable:
        row_rpane = [
        #     timestamp, f"Cruise: {cruise}", f"Vessel: {vessel}", f"Observer: {observer}", f"CTD: {ctd}", f"Dump: {dump_padded}", f"Cast: {cast_padded}", f"Station: {station}",
        #     f"Fath. Depth: {str(fathometer)}", f"Target Depth: {str(target)}", f"Comments: {comments.replace('\n', '\\n')}", f"GPS: {self.current_lat:.6f}", f"{self.current_lon:.6f}"
            timestamp, f"Cruise: {cruise}", f"Vessel: {vessel}", f"Observer: {observer}", f"CTD: {ctd}", f"Dump: {dump_padded}",
            f"Cast: {cast_padded}", f"Station: {station}", f"Fath. Depth: {str(fathometer)}", f"Target Depth: {str(target)}",
            f"GPS: {latitude:.6f}", f"{longitude:.6f}", f"Comments: {comments.replace('\n', '\\n')}"
        ]

        # Write to CSV
        output_csv = "gps_log.csv"
        file_exists = os.path.exists(output_csv) and os.path.getsize(output_csv) > 0
        
        with open(output_csv, 'a', newline='') as f:
            #writer = csv.writer(f)
            # try this option, which hopefully will surround the 'text' fields with double-quotes, automatically:
            writer = csv.writer(f, quoting=csv.QUOTE_NONNUMERIC)

            if not file_exists:
                writer.writerow(["Timestamp", "Cruise", "Vessel", "Observer", "CTD#", "Dump#", "Cast#", "Station", "Fathometer Depth", "Target Depth", "Latitude", "Longitude", "Comments"])
            writer.writerow(row)

        # Display in log
        #self.log_text.append(','.join(row))
        self.log_text.append(', '.join(row_rpane))
        self.log_text.ensureCursorVisible()

        # Clear the station fields:
        for field in self.station_group.findChildren(QLineEdit):
            field.clear()
        #self.station_combo.clear() # This wipes out all the data, so we would have to reload it.
        self.comments_edit.clear()

        # Move the cursor to the first field
        self.cast_edit.setFocus()

        ### end of submit function

    # I could not make this button nice and small; it takes up a third of the row.
    # def create_help_button(self, text):
    #     btn = QPushButton("?")
    #     #btn = QPushButton("ⓘ")
    #     font = btn.font()
    #     font.setPointSize(8)
    #     btn.setFont(font)
    #     btn.setFixedSize(20, 20)
    #     #btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    #     #btn.setStyleSheet("padding: 0px; margin: 0px; font-weight: bold;")
    #     btn.setStyleSheet("font-weight: bold;")
    #     btn.setProperty("help_text", text)
    #     btn.clicked.connect(self.show_widget_help)
    #     return btn

    # def show_widget_help(self):
    #     button = self.sender() # Qt trick that informs which button triggered the event.
    #     help_text = button.property("help_text")
    #
    #     QMessageBox.information(
    #         self,
    #         "Field Help",
    #         help_text
    #     )

    # Placeholders for menu callbacks
    def show_config(self):
        QMessageBox.information(self, "Config", "TODO: Configuration editor to go here...")

    def load_config(self, csv_file=None):
        """Load config CSV into self.config dict."""
        if csv_file is None:
            csv_file = os.path.join(os.path.dirname(__file__), "oc_station_metadata_form_config.csv")

        if not os.path.exists(csv_file):
            msg = f"Config file not found: '{csv_file}'."
            print(msg)
            QMessageBox.warning(self, "Config error", msg)
            return

        try:
            with open(csv_file, newline='', encoding='utf-8') as f:
                filtered = (
                    line for line in f
                    if line.strip() and not line.strip().startswith('#')
                )
                reader = csv.DictReader(filtered)
                self.config = {row['parameter']: row['value'] for row in reader}

                # Optionally convert numeric values
                for k, v in self.config.items():
                    # Lines starting with '#' are comments so skip them:
                    if self.config[k].startswith('#'):
                        continue

                    try:
                        self.config[k] = int(v)
                    except ValueError:
                        try:
                            self.config[k] = float(v)
                        except ValueError:
                            pass  # leave as string
        except Exception:
            msg = f"Failed to load config file: '{csv_file}'."
            print(msg)
            QMessageBox.warning(self, "Config error", msg)
            return

        #QMessageBox.information(self, "Config","Config file loaded:")
        self.statusBar().showMessage("Config file loaded.", 5000)

    def toggle_gps_errors(self, checked):
        #self.show_gps_errors = checked
        QMessageBox.information(self, "GPS", f"GPS error messages are toggled {'ON' if checked else 'OFF'}.")

    def gps_disconnect(self):
        QMessageBox.information(self, "GPS", "Unplug the device, then click 'Refresh Ports'.")

    def show_about(self):
        QMessageBox.information(self, "About", f"GPS Data Entry App v{__version__}\nAuthor: T. Ziomek")

# End of class GPSApp

# Makes a red border around a widget which is not passing input validation.
def mark_invalid(widget):
    widget.setStyleSheet("border: 2px solid red;")
    
# Clears the red border around a widget if it passes input validation.
def clear_invalid(widget):
    widget.setStyleSheet("")

if __name__ == '__main__':
    app = QApplication([])
    window = GPSApp()
    window.show()
    app.exec() # Do not step into this when debugging. It will get lost in the Qt library.