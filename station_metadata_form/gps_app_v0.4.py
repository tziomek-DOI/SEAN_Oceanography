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
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'libs'))
from PyQt6.QtWidgets import (
	QApplication, QMainWindow, QWidget, QFormLayout, QVBoxLayout, QHBoxLayout, QLineEdit, QSplitter, QCheckBox,
	QComboBox, QTextEdit, QPushButton, QLabel, QSplitter, QMessageBox, QVBoxLayout, QTextEdit, QGroupBox, QFrame
)

# Added QThread and pyqtSignal to implement the threaded GPS polling.
from PyQt6.QtCore import QTimer, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
import ctypes
from ctypes import wintypes
import time
from datetime import datetime
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
# This version replaces v0.3a, and should update the gps_label with the coords (it also does course/speed but we might not use that).
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
        try:
            ser = Serial(self.port, self.baudrate, timeout=1)
        except SerialException as e:
            self.error.emit(f"Failed to open GPS port: {e}")
            return

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
                return

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

class GPSApp(QMainWindow):
    def __init__(self):
        super().__init__()

        # Serial connection
        self.ser = None  # Initialize serial port as None
        self.current_lat = None
        self.current_lon = None

        # Window size and title
        self.setWindowTitle("GPS Logger")
        self.resize(1000, 700)

        # Styling
        try:
            with open('stylesheet_minimal.qss', 'r') as file:
                self.setStyleSheet(file.read())
        except FileNotFoundError:
            print("Warning: stylesheet.qss not found, using default styling")
            self.setStyleSheet("""
                QWidget { font-family: Arial; font-size: 12px; }
                QLineEdit, QComboBox, QTextEdit { border: 1px solid #ccc; padding: 5px; }
                QPushButton { background-color: #f0f0f0; border: 1px solid #ccc; padding: 5px; }
            """)

        # Widget definitions
        
        # Replace with a dropdown:
        # self.com_edit = QLineEdit()
        # self.com_edit.setText("COM4")
        self.com_combo = QComboBox()
        for p in list_ports.comports():
            self.com_combo.addItem(p.device, p) # device string, plus full info (if needed)
        
        self.connect_btn = QPushButton("Connect GPS")
        self.connect_btn.clicked.connect(self.connect_gps)
        self.gps_label = QLabel("GPS: Not connected")
        self.cruise_edit = QLineEdit()
        self.vessel_edit = QLineEdit()
        self.observer_edit = QLineEdit()
        self.ctd_combo = QComboBox()
        self.ctd_combo.addItems(["7", "8"])  # Replace with your actual CTD items
        self.dump_edit = QLineEdit()
        self.cast_edit = QLineEdit()
        self.station_combo = QComboBox()
        #self.station_combo.addItems(["S1", "S2", "S3"])  # Replace with your actual Station items
        self.station_combo.addItems(["{:02d}".format(i) for i in range(1, 25)])  # Populates dropdown with 01-24
        self.fathometer_edit = QLineEdit()
        self.target_edit = QLineEdit()
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

        # COM Port and Connect button
        form_top = QFormLayout()
        #form_top.addRow("COM Port:", self.com_edit)
        form_top.addRow("COM Port:", self.com_combo)
        connect_hbox = QHBoxLayout()
        connect_hbox.addStretch()
        connect_hbox.addWidget(self.connect_btn)
        connect_hbox.addStretch()
        self.connect_btn.setFixedWidth(150)  # Fixed width to prevent stretching

        # Grok removed the .addRow for gps_label. See if this works?
        # It displays, but positioned to right of button, not good.
        #form_top.addRow(self.gps_label)
        #connect_hbox.addWidget(self.gps_label)
        
        # Here, Grok slightly modified the code to add a blank area for the gps_label:
        #form_top.addRow(connect_hbox)
        form_top.addRow("", connect_hbox)
        form_top.addRow("GPS Status: ", self.gps_label)
        
        left_layout.addLayout(form_top)

        #left_layout.addWidget(self.gps_label)

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
        station_group = QGroupBox("Station Survey")
        station_form = QFormLayout()
        #station_form.addRow("Dump#:", self.dump_edit)
        station_form.addRow("Cast#:", self.cast_edit)
        station_form.addRow("Station:", self.station_combo)
        station_form.addRow("Fathometer Depth:", self.fathometer_edit)
        station_form.addRow("Target Depth:", self.target_edit)
        station_form.addRow("Comments:", self.comments_edit)
        station_group.setLayout(station_form)
        left_layout.addWidget(station_group)

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

        # Timer for polling GPS
        # self.timer = QTimer()
        # self.timer.timeout.connect(self.poll_gps)
        # self.timer.start(10000)  # Poll every second
        
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
        #port = self.com_edit.text()
        port = self.com_combo.currentText()
        
        self.gps_worker = GPSWorker(port)
        # v0.3a:
        #self.gps_worker.data_received.connect(self.on_gps_data)
        # v0.3b: updates the label with the data:
        self.gps_worker.position_update.connect(self.on_gps_update)
        self.gps_worker.error.connect(self.on_gps_error)
        self.gps_worker.start()

    # Used in v0.3b. Modify the output string as desired.
    # We should add a checkbox or menu option to toggle on/off course/speed?
    def on_gps_update(self, lat, lon, speed, course):
        self.gps_label.setText(
            #f"Lat: {lat:.6f}, Lon: {lon:.6f}"
            f"Lat: {lat:.6f}, Lon: {lon:.6f}\nSpeed: {speed:.1f} kn, Course: {course:.1f}°"
        )

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
            QMessageBox.warning(self, "Error", "GPS not connected.")
            return

        # Force a read from the GPS device:
        lat, lon = self.gps_worker.get_latest_position()
        
        #if self.current_lat is None or self.current_lon is None:
        if lat is None or lon is None:
            QMessageBox.warning(self, "Error", "No GPS data available")
            return
        
        self.current_lat = lat
        self.current_lon = lon

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
            "Target Depth": target_str
        }
        for name, value in required_fields.items():
            if not value:
                QMessageBox.warning(self, "Error", f"{name} is required")
                return

        # Validate integers and max lengths, with per-field messages
        # ChatGPT version should give better feedback.
        errors = []

        # Reset all invalid UI indicators first.
        for w in [self.cruise_edit, self.vessel_edit, self.observer_edit, self.dump_edit, self.cast_edit, self.fathometer_edit, self.target_edit, self.comments_edit]:
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
        if not (1 < len(observer) <= 40):
            errors.append("Observer must be 1-40 characters.")
            mark_invalid(self.observer_edit)
            
        # --- Dump ---
        if not dump_str.isdigit() or len(dump_str) != 4:
            errors.append("Dump must be 4 integers (pad with leading 0, such as '0334').")
            mark_invalid(self.dump_edit)

        # --- Cast ---
        if not cast_str.isdigit() or not (1 <= len(cast_str) <= 3):
            errors.append("Cast must be numeric, between 1 to 3 digits.")
            mark_invalid(self.cast_edit)

        # --- Fathometer depth ---
        if not fathometer_str.isdigit() or not (1 <= len(fathometer_str) <= 3):
            errors.append("Fathometer depth must be numeric, between 1 to 3 digits.")
            mark_invalid(self.fathometer_edit)

        # --- Target depth ---
        if not target_str.isdigit() or not (1 <= len(target_str) <= 3):
            errors.append("Target depth must be numeric, between 1 to 3 digits.")
            mark_invalid(self.target_edit)

        # --- Comments ---
        if len(comments) > 1000:
            errors.append("Comments must be 1000 characters or less.")
            mark_invalid(self.comments_edit)

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

        # Do we want UTC time instead??
        #timestamp = datetime.now().isoformat()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        dump_padded = f"{dump:04d}"
        cast_padded = f"{cast:03d}"
#        row = [
#            timestamp, cruise, vessel, observer, ctd, dump_padded, cast_padded, station,
#            str(fathometer), str(target), comments.replace('\n', '\\n').replace(',', '\\,'),
#            f"{self.current_lat:.6f}", f"{self.current_lon:.6f}"
#        ]
		# We do not need to escape the Comments field in the above manner.
        row = [
            timestamp, cruise, vessel, observer, ctd, dump_padded, cast_padded, station,
            str(fathometer), str(target), comments.replace('\n', '\\n'), f"{self.current_lat:.6f}", f"{self.current_lon:.6f}"
        ]
        
        # Let us customize the output on the right-side pane to make it more readable:
        row_rpane = [
            timestamp, f"Cruise: {cruise}", f"Vessel: {vessel}", f"Observer: {observer}", f"CTD: {ctd}", f"Dump: {dump_padded}", f"Cast: {cast_padded}", f"Station: {station}",
            f"Fath. Depth: {str(fathometer)}", f"Target Depth: {str(target)}", f"Comments: {comments.replace('\n', '\\n')}", f"GPS: {self.current_lat:.6f}", f"{self.current_lon:.6f}"
        ]

        # Write to CSV
        file_exists = os.path.exists('gps_log.csv') and os.path.getsize('gps_log.csv') > 0
        
        with open('gps_log.csv', 'a', newline='') as f:
            writer = csv.writer(f)
            
            if not file_exists:
                writer.writerow(["Timestamp", "Cruise", "Vessel", "Observer", "CTD#", "Dump#", "Cast#", "Station", "Fathometer Depth", "Target Depth", "Comments", "Latitude", "Longitude"])
            writer.writerow(row)

        # Display in log
        #self.log_text.append(','.join(row))
        self.log_text.append(', '.join(row_rpane))
        self.log_text.ensureCursorVisible()

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
    app.exec()