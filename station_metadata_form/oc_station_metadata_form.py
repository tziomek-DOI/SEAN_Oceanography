# oc_station_metadata_form.py
# Author: T. Ziomek with AI help (ChatGPT and Grok)
#
# Change log
# v0.7.0
# A number of bug fixes and UI tweaks were made, to allow more seamless disconnecting from GPS.
# In practice, one external USB device would be shared between two separate apps - this one, and SeaLog.
# So, having a clean disconnect seems necessary, as SeaLog tends to be very finicky in connecting to GPS pucks.
# New QListWidget on right-side pane allows for editing of records, which persist as JSON.
# New menu options to export CSV, and load/save the data (JSON) files.
#
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
    QApplication, QMainWindow, QWidget, QFormLayout, QVBoxLayout, QHBoxLayout, QLineEdit, QCheckBox, QFileDialog,
    QComboBox, QTextEdit, QPushButton, QLabel, QSplitter, QMessageBox, QGroupBox, QFrame, QListWidget, QListWidgetItem
)

# Added QThread and pyqtSignal to implement the threaded GPS polling.
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QDoubleValidator, QIntValidator, QAction

import time
from datetime import datetime, UTC
import csv
from libs.serial import Serial, SerialException  # Assuming your libs/serial for GPS connection
from libs.serial.tools import list_ports  # This will feed a dropdown with available COM ports/devices
import json  # Use JSON to manipulate records. A CSV export would be done separately.

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
    status = pyqtSignal(str)

    def __init__(self, port, baudrate=4800, parent=None):
        super().__init__(parent)
        self.port = port
        self.baudrate = baudrate
        self._running = True
        self._has_fix = False
        self.current_lat = None
        self.current_lon = None

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
            # 2026-03-30: Fixed submit so that we can return from errors here properly (uncommented).
            return

        # Handshake timeout (wait for valid NMEA sentence)
        start_time = time.time()
        got_fix = False
        self._has_fix = False

        while self._running:
            try:
                # if not ser:
                #     # Raise an exception. If the port is already in use (by SeaLog), this gets messy
                #     raise SerialException("Check if serial port is already in use.\nTry refreshing the ports.")
                line = ser.readline().decode(errors="ignore").strip()

                if line.startswith("$GPRMC"):
                    parsed = self.parse_gprmc(line)
                    if parsed:
                        lat, lon, speed, course = parsed
                        self.position_update.emit(lat, lon, speed, course)
                        self.current_lat = lat
                        self.current_lon = lon
                        got_fix = True
                        self._has_fix = True
                        # Try sending the 'connected' alert to the user here (should be just one-time):
                        self.status.emit("GPS Connected. Check status bar (lower right).")
                        break  # handshake succeeded

            except SerialException as e:
                self.error.emit(f"GPS read error: {e}")
                self._has_fix = False
                if ser and ser.is_open:
                    ser.close()
                # 2026-03-05:
                # Commented out return so we can manually enter GPS coords from another source.
                # (otherwise, code will not allow form to be submitted)
                # Uncommented on 2026-03-30 with proper submit.
                return

            # Timeout if no valid data
            if not got_fix and (time.time() - start_time > 5):
                self.error.emit("No valid GPS data received (timeout). Check COM port.\nInitial connection may take a few minutes.")
                if ser and ser.is_open:
                    ser.close()
                return

        # Main loop after handshake
        while self._running and got_fix:
            try:
                # if not ser:
                #     # Raise an exception. If the port is already in use (by SeaLog), this gets messy
                #     raise SerialException("Check if serial port is already in use.\nTry refreshing the ports.")
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

        if ser and ser.is_open:
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

    def clear_coordinates(self):
        self.current_lat = None
        self.current_lon = None

    def has_fix(self):
        return self._has_fix


# This class defines the overall application structure, particularly the UI.
class GPSApp(QMainWindow):
    def __init__(self):
        super().__init__()

        # Set the 'config' and 'data' subdirs:
        try:
            self.config_dir = os.path.join(os.path.dirname(__file__), 'config')  # 'config' is subdir of app dir
            self.data_dir = os.path.join(os.path.dirname(__file__), 'data')  # 'config' is subdir of app dir
        except FileNotFoundError as e:
            QMessageBox.warning(
                self,
                "Config Error!", "There must be a 'config' and 'data' subdirectory with the app!\n"
                                 "Please create these directories and retry."
            )
            print(f"Missing 'config' and/or 'data' subdirectories. Error: {e}")
            return
        except OSError as e:
            QMessageBox.warning(
                self,
                "Config Error!", "There must be a 'config' and 'data' subdirectory with the app!\n"
                                 "Please create these directories and retry."
            )
            print(f"Missing 'config' and/or 'data' subdirectories. Error: {e}")
            return

        # Load the config CSV file:
        self.config = {} # will store key/value pairs
        self.statusBar().showMessage("Loading config file...")
        self.load_config()
        self.statusBar().showMessage("Config file loaded.", 5000)

        # set the name of the JSON file used to store records (separate from the CSV export file)
        # Load default JSON file which stores the records:
        json_recs_default_filename = self.config.get("json_records", "oc_station_metadata_form_records.json")
        self.json_recs_file_default = os.path.join(self.data_dir, json_recs_default_filename)

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
        self.connect_btn.clicked.connect(self.toggle_gps_connection)
        self.connect_btn.setStyleSheet("background-color: red; color: white;")
        self.gps_connected = False  # this will be used in toggling GPS on/off using gps_connect
        self.gps_label = QLabel("GPS: Not connected")
        self.statusBar().addPermanentWidget(self.gps_label) # status bar will always be connected to GPS messages

        self.cruise_edit = QLineEdit()
        self.cruise_max_len = self.config.get('cruise_max_length', 20)
        self.cruise_edit.setMaxLength(self.cruise_max_len)
        self.vessel_edit = QLineEdit()
        self.vessel_max_len = self.config.get('vessel_max_length', 24)
        self.vessel_edit.setMaxLength(self.vessel_max_len)
        self.observer_edit = QLineEdit()
        self.observer_max_len = self.config.get('observer_max_length', 50)
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
        self.current_coords_btn = QPushButton("Get Current Coordinates")
        self.current_coords_btn.clicked.connect(self.get_current_coordinates)
        self.comments_edit = CustomTextEdit()
        self.comments_max_len = self.config.get('comments_max_length', 512)
        self.comments_edit.setMaximumHeight(self.comments_max_len)
        self.submit_btn = QPushButton("Submit")
        self.submit_btn.clicked.connect(self.submit)
        self.clear_btn = QPushButton("Clear fields")
        self.clear_btn.clicked.connect(self.cancel_clear)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)

        # Using a QListWidget for the right side logging and edit functionality.
        self.log_list = QListWidget()
        self.log_list.itemClicked.connect(self.load_record)
        self.current_item = None # Used by the QListWidget when clicking to access existing items.
        # Load the default records file (set in the config file):
        self.load_metadata_records(self.json_recs_file_default)
        # If user loads a different file, it will become 'current'. 'Default' should always work on startup.
        self.json_recs_file_current = self.json_recs_file_default

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

        # Checkbox that disables the GPS worker, allowing user to manually enter coordinates:
        # self.chk_disable_gps = QCheckBox("Disable GPS")
        # self.chk_disable_gps.stateChanged.connect(self.toggle_gps_worker)
        # left_layout.addWidget(self.chk_disable_gps)
        
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

        coords_hbox = QHBoxLayout()
        coords_hbox.addWidget(self.current_coords_btn)
        coords_hbox.addStretch()
        station_form.addRow("", coords_hbox)

        station_form.addRow("Comments:", self.comments_edit)
        self.station_group.setLayout(station_form)
        left_layout.addWidget(self.station_group)

        # Submit and Clear buttons
        buttons_hbox = QHBoxLayout()
        buttons_hbox.addStretch()
        buttons_hbox.addWidget(self.submit_btn)
        buttons_hbox.addWidget(self.clear_btn)
        buttons_hbox.addStretch()
        self.submit_btn.setFixedWidth(150)  # Fixed width to prevent stretching
        self.clear_btn.setFixedWidth(150)
        left_layout.addLayout(buttons_hbox)

        left_layout.addStretch()  # Push content up and allow scaling

        # Right pane: Log
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(10, 10, 10, 10)
        #right_layout.addWidget(self.log_text)
        # Add a label above the widget to identify the fields (hacky):
        self.log_list_header = QLabel("Cast | Station | Timestamp")
        self.log_list_header.setStyleSheet("font-family: monospace; font-weight: bold;")
        self.log_list.setStyleSheet("font-family: monospace;")
        right_layout.addWidget(self.log_list_header)
        right_layout.addWidget(self.log_list)

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
                "&Load Data File": self.open_metadata_file,
                "S&ave Data File As...": self.save_metadata_file_as,
                "&Export CSV File": self.export_csv,
                "E&xit": self.close
            },
            "&Settings": {
                "&Config File": self.show_config,
                f"{gps_errors_str}": self.toggle_gps_errors,
                "Refresh S&tyles": self.load_stylesheet
            },
            "&GPS": {
                "Connect": self.toggle_gps_connection,
                "Disconnect": self.toggle_gps_connection,
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
        ss_name = "stylesheet_minimal.qss"
        ss = os.path.join(self.config_dir, ss_name)
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

    def open_metadata_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Metadata File", "", "JSON Files (*.json);;All Files (*)"
        )

        # If user cancels:
        if not file_path:
            return

        self.load_metadata_records(file_path)
        self.json_recs_file_current = file_path

    def save_metadata_file_as(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save As",
            "",
            "JSON Files (*.json)"
        )

        # if user cancels:
        if not file_path:
            return

        try:
            records = []
            for i in range(self.log_list.count()):
                item = self.log_list.item(i)
                records.append(item.data(Qt.ItemDataRole.UserRole))

            with open(file_path, "w") as f:
                json.dump(records, f, indent=2)

            self.json_recs_file_current = file_path
        except OSError as e:
            msg = f"Save failed: {e}"
            print(msg)
            QMessageBox.warning(self, "File Error", msg)

    # load_metadata_records
    # Called on app startup, and loads the file specified in the config file.
    # User can also open a different file via the File...Open menu, and this function
    # is reused to load the records.
    def load_metadata_records(self, file_path):
        # Load the records from the file into the QListWidget:
        self.log_list.clear()
        self.current_item = None

        try:
            with open(file_path, "r") as f:
                records = json.load(f)
        except FileNotFoundError:
            msg = f"Metadata file '{file_path}' not found. Creating new (empty) file."
            QMessageBox.warning(self, "Load Metadata Error", msg)
            print(msg)

            # Create an empty file so the user does not have to. This technically should not happen, but...
            # JSON files should start as a blank list []
            records = []
            try:
                with open(file_path, "w") as f:
                    json.dump(records, f, indent=2)
                QMessageBox.information(
                    self, "Metadata records", "Use File -> Save As... to rename the default file."
                )
            except OSError as e:
                msg = f"Error creating metadata file '{file_path}'.\nTry creating the file manually."
                QMessageBox.warning(self, "Load Metadata Error", msg)
                print(f"{msg}Error details: {e}")

            return
        except json.JSONDecodeError:
            msg = f"Invalid metadata file '{file_path}'.\nCheck JSON formatting."
            QMessageBox.warning(self, "Load Metadata Error", msg)
            print(msg)
            return
        except OSError as e:
            msg = f"Error loading metadata file '{file_path}'."
            QMessageBox.warning(self, "Load Metadata Error", msg)
            print(f"{msg}Error details:\n{e}")
            return

        record_count = 0
        for record in records:
            display = f"{record['cast']} | {record['station']} | {record['eventDate']}"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, record)
            self.log_list.addItem(item)
            record_count += 1

        if record_count == 0:
            QMessageBox.information(
                self, "Load records",
                "If this is a new survey, recommend using File->Save As to rename the default data file."
            )
        self.gps_label.setText(f"{record_count} records loaded.")

    # When the app is closed, some actions might need to be taken before the app shuts down.
    def closeEvent(self, event):

        # If the user has not saved to a file different than the default, prompt them:
        if self.json_recs_file_current == self.json_recs_file_default:
            # event.accept()
            # return

            reply = QMessageBox.question(
                self, "Save Changes?",
                "Currently using the default data file.\n"
                "Would you like to save the data to a different file before exiting?",
                QMessageBox.StandardButton.Yes |
                QMessageBox.StandardButton.No |
                QMessageBox.StandardButton.Cancel
            )

            if reply != QMessageBox.StandardButton.Cancel:
                # Shut down the GPS worker cleanly:
                if hasattr(self, "gps_worker") and self.gps_worker:
                    self.gps_worker.stop()

                if reply == QMessageBox.StandardButton.Yes:
                    self.save_metadata_file_as()
                event.accept()
                super().closeEvent(event)
            else:
                event.ignore()
        else:
            # Shut down the GPS worker cleanly:
            if hasattr(self, "gps_worker") and self.gps_worker:
                self.gps_worker.stop()
            super().closeEvent(event)

    # Exports the JSON-formatted data into a CSV file.
    def export_csv(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export CSV",
            "",
            "CSV Files (*.csv)"
        )

        # if user clicks Cancel:
        if not file_path:
            return

        field_order = [
            "eventDate", "cruise", "vessel", "observers", "ctd", "dump", "cast", "station",
            "fathometer_depth", "target_depth", "decimalLatitude", "decimalLongitude", "fieldNotes"
        ]

        try:
            with open(file_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=field_order, quoting=csv.QUOTE_NONNUMERIC)
                writer.writeheader()

                for i in range(self.log_list.count()):
                    item = self.log_list.item(i)
                    record = item.data(Qt.ItemDataRole.UserRole)
                    writer.writerow(record)

            QMessageBox.information(self, "Export CSV", "CSV Export complete.")
        except OSError as e:
            msg = f"CSV export failed\n({e})"
            QMessageBox.warning(self, "Export CSV", msg)
            print(msg)

    # Check box functionality to toggle RO/RW of cruise details widgets.
    # def toggle_cruise_lock(self, state):
    def toggle_cruise_lock(self, _):
        
        is_locked = self.lock_cruise_chk.isChecked()

        if __debug__:
            print("Toggle cruise lock: ", is_locked)
        
        self.cruise_edit.setReadOnly(is_locked)
        self.vessel_edit.setReadOnly(is_locked)
        self.observer_edit.setReadOnly(is_locked)
        self.ctd_combo.setEnabled(not is_locked)
        self.dump_edit.setReadOnly(is_locked)

    def toggle_gps_connection(self):
        if not self.gps_connected:
            self.gps_connect()
        else:
            self.gps_disconnect()

    # def toggle_gps_worker(self):
    #     if self.gps_worker_active:
    #         self.gps_worker_active = False
    #     else:
    #         QMessageBox.information(self, "GPS", "Make sure no other devices/apps are\nusing the GPS port before connecting.")
    #         self.gps_worker_active = True

    # ChatGPT offered this set of functions which are used to implement the QThread-based GPS functionality:
    def gps_connect(self):
        print(f"connect: self id = {id(self)}")

        # if not self.gps_worker_active:
        #     QMessageBox.warning(self, "GPS Error","GPS is currently disabled.\nUncheck the box and retry.")
        #     return

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

        # Instead of the popup, which is clunky, write to the right pane but don't write to the CSV
        #QMessageBox.information(self, "GPS", "Connecting to GPS.\nThis may take a few minutes.\nCheck status at lower right corner.")
        self.log_text.append("\n*** Connecting to GPS... this may take a few minutes.\nCheck status at lower right corner.***\n")

        # Here, we reassign the button to disconnect and change the label and color:
        # Maybe cannot do this here since worker might not connect fast enough or might fail.
        #self.connect_btn.setText("Disconnect GPS")
        #self.connect_btn.setStyleSheet("background-color: green; color: white;")

    def gps_disconnect(self):
        print(f"disconnect: self id = {id(self)}")
        if self.gps_worker:
            self.gps_worker.stop() # this doesnt work (gps_worker is None). # Could try .requestInterruption() pattern.

        #QMessageBox.information(self, "GPS", "GPS disconnected. Unplug the device, then click 'Refresh Ports'.")
        QMessageBox.information(self, "GPS", "GPS disconnected.")
        self.gps_connected = False
        self.connect_btn.setText("Connect GPS")
        self.connect_btn.setStyleSheet("background-color: red; color: white;")
        self.gps_label.setText("GPS Disconnected.")
        self.current_lat = None
        self.current_lon = None
        self.gps_worker.current_lon = None
        self.gps_worker.current_lat = None
        self.latitude_edit.setText("")
        self.longitude_edit.setText("")

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
        # If this is the initial connection to the GPS, we can use the 'first fix'
        # to send a message to the user, and update the gps toggle variable and button UI:
        if not self.gps_connected:
            self.gps_connected = True
            QMessageBox.information(self, "GPS", "GPS Connected.")
            self.connect_btn.setStyleSheet("background-color: green; text: white;")
            self.connect_btn.setText("Disconnect GPS")

        self.gps_label.setText(
            f"Lat: {lat:.6f}, Lon: {lon:.6f}, Speed: {speed:.1f} kn, Course: {course:.1f}° "
        )
        # We don't want to keep updating the UI like this.
        # If the user is in 'edit' mode, we dont want to change these with updated coordinates
        # unless the user manually edits it.
        # self.latitude_edit.setText(f"{lat:.6f}")
        # self.longitude_edit.setText(f"{lon:.6f}")

        # Store the current coords, and use only when needed:
        self.current_lat = lat
        self.current_lon = lon

    def get_current_coordinates(self):
        if self.gps_connected:
            self.latitude_edit.setText(f"{self.current_lat:.6f}")
            self.longitude_edit.setText(f"{self.current_lon:.6f}")
        else:
            QMessageBox.warning(self, "GPS Error", "GPS not connected.")

    def on_gps_data(self, line):
        if line.startswith("$GP"):  # NMEA detected
            self.gps_label.setText("Connected...acquiring coordinates...")
            # Later: parse GPGGA / GPRMC here and update map with coordinates

    def on_gps_status(self, msg):
        #QMessageBox.information(self, "Status update", msg)
        #self.gps_label.setText("No GPS available on selected COM port.")
        self.gps_label.setText(msg)

    def on_gps_error(self, msg):
        QMessageBox.critical(self, "GPS Error", msg)
        #self.gps_label.setText("No GPS available on selected COM port.")
        self.gps_label.setText(msg)
        self.connect_btn.setText("Connect GPS")
        self.connect_btn.setStyleSheet("background-color: red; color: white;")

        if self.gps_worker and self.gps_worker.isRunning():
            self.gps_worker.stop()
            #self.gps_worker.requestInterruption()
            #self.gps_worker.wait()

        self.gps_worker = None

    # def closeEvent(self, event):
    #     if hasattr(self, "gps_worker") and self.gps_worker:
    #         self.gps_worker.stop()
    #     super().closeEvent(event)
    
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

        # TODO: We only want to get the current position for NEW entries, or manual lat/long edits!
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
            # 4/2/26: disabled this. If the user is in 'edit' mode, we don't want to automatically
            # overwrite the lat/long. The new button allows them to grab current coordinates if needed.
            #self.latitude_edit.setText(f"{lat:0.6f}")
            #self.longitude_edit.setText(f"{lon:0.6f}")

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
        # required_fields = {
        #     "Cruise": cruise,
        #     "Vessel": vessel,
        #     "Observer": observer,
        #     "CTD#": ctd,
        #     "Dump#": dump_str,
        #     "Cast#": cast_str,
        #     "Station": station,
        #     "Fathometer Depth": fathometer_str,
        #     "Target Depth": target_str,
        #     "Latitude": latitude_str,
        #     "Longitude": longitude_str
        # }

        required_fields = {
            "Cruise": {
                "name": "Cruise",
                "value": cruise,
                "widget": self.cruise_edit
            },
            "Vessel": {
                "name": "Vessel",
                "value": vessel,
                "widget": self.vessel_edit
            },
            "Observer": {
                "name": "Observer",
                "value": observer,
                "widget": self.observer_edit
            },
            "CTD#": {
                "name": "CTD#",
                "value": ctd,
                "widget": self.ctd_combo
            },
            "Dump#": {
                "name": "Dump#",
                "value": dump_str,
                "widget": self.dump_edit
            },
            "Cast#": {
                "name": "Cast#",
                "value": cast_str,
                "widget": self.cast_edit
            },
            "Station": {
                "name": "Station",
                "value": station,
                "widget": self.station_combo
            },
            "Fathometer Depth": {
                "name": "Fathometer Depth",
                "value": fathometer_str,
                "widget": self.fathometer_edit
            },
            "Target Depth": {
                "name": "Target Depth",
                "value": target_str,
                "widget": self.target_edit
            },
            "Latitude": {
                "name": "Latitude",
                "value": latitude_str,
                "widget": self.latitude_edit
            },
            "Longitude": {
                "name": "Longitude",
                "value": longitude_str,
                "widget": self.longitude_edit
            }
        }

        # for name, value in required_fields.items():
        #     if not value:
        #         QMessageBox.warning(self, "Error", f"{name} is required")
        #         return
        for field in required_fields.values():
            if not field["value"]:
                QMessageBox.warning(self, "Error", f"{field['name']} is required.")
                mark_invalid(field['widget'])
                field['widget'].setFocus()
                return
            else:
                clear_invalid(field['widget'])

        # Validate integers and max lengths, with per-field messages
        # ChatGPT version should give better feedback.
        errors = []

        # Reset all invalid UI indicators first.
        for w in [self.cruise_edit, self.vessel_edit, self.observer_edit, self.dump_edit, self.cast_edit,
                  self.fathometer_edit, self.target_edit, self.comments_edit, self.latitude_edit, self.longitude_edit]:
            clear_invalid(w)

        first_invalid_field = None

        # region Validation block
        # --- Cruise ---
        if not (1 <= len(cruise) <= 30):
            errors.append("Cruise must be 1-30 characters.")
            mark_invalid(self.cruise_edit)
            first_invalid_field = self.cruise_edit
            
        # --- Vessel ---
        if not (1 <= len(vessel) <= 20):
            errors.append("Vessel must be 1-20 characters.")
            mark_invalid(self.vessel_edit)
            if not first_invalid_field:
                first_invalid_field = self.vessel_edit
            
        # --- Observer ---
        if not (2 <= len(observer) <= self.observer_max_len):
            errors.append(f"Observer must be 2-{self.observer_max_len} characters.")
            mark_invalid(self.observer_edit)
            if not first_invalid_field:
                first_invalid_field = self.observer_edit
            
        # --- Dump ---
        if not dump_str.isdigit() or len(dump_str) != 4:
            errors.append("Dump must be 4 integers (pad with leading 0, such as '0334').")
            mark_invalid(self.dump_edit)
            if not first_invalid_field:
                first_invalid_field = self.dump_edit

        # --- Cast ---
        if not cast_str.isdigit() or not (1 <= len(cast_str) <= 3):
            errors.append("Cast must be numeric, between 1 to 3 digits.")
            mark_invalid(self.cast_edit)
            if not first_invalid_field:
                first_invalid_field = self.cast_edit

        # --- Fathometer depth ---
        if not fathometer_str.isdigit() or not (1 <= len(fathometer_str) <= 3):
            errors.append("Fathometer depth must be numeric, between 1 to 3 digits.")
            mark_invalid(self.fathometer_edit)
            if not first_invalid_field:
                first_invalid_field = self.fathometer_edit

        # --- Target depth ---
        if not target_str.isdigit() or not (1 <= len(target_str) <= 3):
            errors.append("Target depth must be numeric, between 1 to 3 digits.")
            mark_invalid(self.target_edit)
            if not first_invalid_field:
                first_invalid_field = self.target_edit

        # --- Comments ---
        if len(comments) > 1000:
            errors.append("Comments must be 1000 characters or less.")
            mark_invalid(self.comments_edit)
            if not first_invalid_field:
                first_invalid_field = self.comments_edit

        # --- Latitude ---
        latitude = None
        try:
            latitude = float(latitude_str)
            if not (self.latitude_min <= latitude <= self.latitude_max):
                raise ValueError
        except ValueError:
            errors.append(f"Latitude must be a decimal value, between {self.latitude_min} and {self.latitude_max}.")
            mark_invalid(self.latitude_edit)
            if not first_invalid_field:
                first_invalid_field = self.latitude_edit

        # --- Longitude ---
        longitude = None
        try:
            longitude = float(longitude_str)
            if not (self.longitude_min <= longitude <= self.longitude_max):
                raise ValueError
        except ValueError:
            errors.append(f"Longitude must be a decimal value, between {self.longitude_min} and {self.longitude_max}.")
            mark_invalid(self.longitude_edit)
            if not first_invalid_field:
                first_invalid_field = self.longitude_edit

        # If any errors, show them all at once
        if errors:
            QMessageBox.warning(
                self,
                "Input Error",
                "\n".join(errors)
            )
            if first_invalid_field:
                first_invalid_field.setFocus()
            return

        # If no errors, safe to convert to int
        dump = int(dump_str)
        cast = int(cast_str)
        fathometer = int(fathometer_str)
        target = int(target_str)
        # endregion Validation block

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
            # f"\n{timestamp}", f"Cruise: {cruise}", f"Vessel: {vessel}", f"Observer: {observer}", f"CTD: {ctd}", f"Dump: {dump_padded}",
            # f"Cast: {cast_padded}", f"Station: {station}", f"Fath. Depth: {str(fathometer)}", f"Target Depth: {str(target)}",
            # f"GPS: {latitude:.6f}", f"{longitude:.6f}", f"Comments: {comments.replace('\n', '\\n')}"
            f"\n{timestamp}\nCruise: {cruise}\nVessel: {vessel}\nObserver: {observer}\nCTD: {ctd}"
            f"\nDump: {dump_padded}\nCast: {cast_padded}\nStation: {station}\nFathometer Depth: {str(fathometer)}"
            f"\nTarget Depth: {str(target)}\nlatitude: {latitude:.6f}, longitude: {longitude:.6f}"
            f"\nComments: {comments.replace('\n', '\\n')}"
        ]

        # Write to CSV
        # TODO: Disable CSV writing once testing complete.
        output_csv_name = "gps_log.csv"
        output_csv = os.path.join(self.data_dir, output_csv_name)
        file_exists = os.path.exists(output_csv) and os.path.getsize(output_csv) > 0
        
        with open(output_csv, 'a', newline='') as f:
            # try this option, which hopefully will surround the 'text' fields with double-quotes, automatically:
            writer = csv.writer(f, quoting=csv.QUOTE_NONNUMERIC)

            if not file_exists:
                writer.writerow([
                    "eventDate", "cruise", "vessel", "observers", "ctd", "dump", "cast", "station",
                    "fathometer_depth", "target_depth", "decimalLatitude", "decimalLongitude", "fieldNotes"
                ])
            writer.writerow(row)

        # Display in log (text version)
        # self.log_text.append(', '.join(row_rpane))
        # self.log_text.ensureCursorVisible()

        # Write records to the QListWidget:
        record = {
            "eventDate": timestamp,
            "cruise": cruise,
            "vessel": vessel,
            "observers": observer,
            "ctd": ctd,
            "dump": dump_padded,
            "cast": cast_padded,
            "station": station,
            "fathometer_depth": fathometer,
            "target_depth": target,
            #"decimalLatitude": round(latitude,self.latitude_precision),
            "decimalLatitude": round(float(self.latitude_edit.text()), self.latitude_precision),
            #"decimalLongitude": round(longitude,self.longitude_precision),
            "decimalLongitude": round(float(self.longitude_edit.text()), self.longitude_precision),
            "fieldNotes": comments.replace('\n', '\\n')
        }

        # If the user clicked to 'edit', the current_item will be True.
        # We load the existing record, reset the timestamp to preserve the original,
        # then update the record display (in case cast/station changed).
        # TODO: Do we ever want timestamp to be 'editable'? For now... no.
        if self.current_item:
            # Update the existing record
            # First, load the existing record:
            record_existing = self.current_item.data(Qt.ItemDataRole.UserRole).copy()
            # We do not want to update the timestamp
            record['eventDate'] = record_existing['eventDate']

            # Create a short record identifier for the right-side QListWidget:
            # This is duplicated code (also in 'else') but uses the old eventDate. Messy!
            record_display = f"{record['cast']} | {record['station']} | {record['eventDate']}"

            self.current_item.setText(record_display)
            self.current_item.setData(Qt.ItemDataRole.UserRole, record)
        else:
            # Create a new record
            # Create a short record identifier for the right-side QListWidget:
            record_display = f"{record['cast']} | {record['station']} | {record['eventDate']}"
            item = QListWidgetItem(record_display)
            item.setData(Qt.ItemDataRole.UserRole, record)
            # Add to the widget:
            self.log_list.addItem(item)

        # Clear these so that we don't accidentally overwrite an edited record:
        self.current_item = None
        self.log_list.clearSelection()

        # Clear the station fields:
        for field in self.station_group.findChildren(QLineEdit):
            field.clear()
        self.comments_edit.clear()

        # Move the cursor to the first field
        self.cast_edit.setFocus()

        # Update the JSON records file:
        self.save_records()

        # end of submit function

    # region test_stuff, probably can delete
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
    # end region test_stuff

    # The cancel_clear button clears the UI entries to allow the user to start a new record.

    # save_records
    # Persist items from the QListWidget upon user submit.
    def save_records(self):
        records = []

        for i in range(self.log_list.count()):
            item = self.log_list.item(i)
            record = item.data(Qt.ItemDataRole.UserRole)
            records.append(record)

        try:
            with open(self.json_recs_file_current, "w") as f:
                json.dump(records, f, indent=2)
        except OSError as e:
            QMessageBox.warning(self, "Save Error",
                                "Failed to save the records to file.\n"
                                "Please check the 'json_records' entry in the config file")
            print(f"Failed to save records to the JSON file. Error:\n{e}")

    def cancel_clear(self):
        self.current_item = None # prevents updating an existing item, if it had been clicked.
        form_fields = []
        if not self.lock_cruise_chk.isChecked():
            form_fields.extend([
                self.cruise_edit,
                self.vessel_edit,
                self.observer_edit,
                self.dump_edit
            ])

        form_fields.extend([
            self.cast_edit,
            self.fathometer_edit,
            self.target_edit,
            self.comments_edit,
            self.latitude_edit,
            self.longitude_edit
        ])

        for field in form_fields:
            field.clear()

        self.log_list.clearSelection()  # Removes the selection highlight since we are now dealing with a new record.
        self.log_list.clearFocus()      # might change this to set the focus elsewhere.

    # load_record:
    # If user clicks a record on the right-side list of items, the record gets
    # reloaded into the UI fields and made editable.
    def load_record(self, item):
        self.current_item = item
        self.toggle_cruise_lock(False)

        record = item.data(Qt.ItemDataRole.UserRole)
        self.cruise_edit.setText(record['cruise'])
        self.vessel_edit.setText(record['vessel'])
        self.observer_edit.setText(record['observers'])
        self.ctd_combo.setCurrentText(record['ctd'])
        self.dump_edit.setText(record['dump'])
        self.cast_edit.setText(record['cast'])
        self.station_combo.setCurrentText(record['station'])
        self.fathometer_edit.setText(str(record['fathometer_depth']))
        self.target_edit.setText(str(record['target_depth']))
        self.latitude_edit.setText(f"{float(record['decimalLatitude']):.6f}")
        self.longitude_edit.setText(f"{float(record['decimalLongitude']):.6f}")
        self.comments_edit.setText(record['fieldNotes'])

    # Placeholders for menu callbacks
    def show_config(self):
        QMessageBox.information(self, "Config", "TODO: Configuration editor to go here...")

    def load_config(self, config_file=None):
        """Load config CSV into self.config dict."""
        if config_file is None:
            config_filename = "oc_station_metadata_form_config.csv"
            config_file = os.path.join(self.config_dir, config_filename)

        if not os.path.exists(config_file):
            msg = f"Config file not found: '{config_file}'."
            print(msg)
            QMessageBox.warning(self, "Config error", msg)
            return

        try:
            with open(config_file, newline='', encoding='utf-8') as f:
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
        except OSError as e:
            msg = f"Failed to load config file: '{config_file}'."
            print(f"{msg}Error: {e}")
            QMessageBox.warning(self, "Config error", msg)
            return

        self.statusBar().showMessage("Config file loaded.", 5000)

    def toggle_gps_errors(self, checked):
        QMessageBox.information(self, "GPS", f"GPS error messages are toggled {'ON' if checked else 'OFF'}.")

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
