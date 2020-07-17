import re
import sys

from vibrometer import SignalAnalysis
import sounddevice as sd
from vibrometer import DEV_NAME

import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.animation import FuncAnimation
from PyQt5.QtWidgets import (QApplication, QLabel, QGroupBox, QWidget, QComboBox, QWidget,
                             QPushButton, QVBoxLayout, QHBoxLayout, QLineEdit, QGridLayout,
                             QMainWindow, QFormLayout, QSlider, QTableWidget,
                             QTableWidgetItem)
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import QRunnable, QThreadPool, pyqtSlot
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
import numpy as np
from time import sleep
import random
import queue

q = queue.Queue()
mapping = [c - 1 for c in [1]]


class Window(QMainWindow):
    """Docstring for Window. """
    def __init__(self):
        """TODO: to be defined. """
        super().__init__()
        self.threadpool = QThreadPool()

        self.initUI()

    def initUI(self):
        self.statusBar().showMessage('Ready')
        # self.setGeometry(300, 300, 250, 150)
        self.setWindowTitle('Statusbar')
        self.main_widget = QWidget(self)

        grid = QGridLayout(self.main_widget)
        self.setLayout(grid)

        #############################################################
        # VELO
        group_velo = QGroupBox("VIB-E-220")
        form_time = QFormLayout()
        group_velo.setLayout(form_time)
        self.cbox_vel = QComboBox()
        self.cbox_vel.setFixedWidth(80)
        self.cbox_vel.addItem("20")
        self.cbox_vel.addItem("100")
        self.cbox_vel.addItem("500")
        form_time.addRow(QLabel("VELO (mm/s):"), self.cbox_vel)
        grid.addWidget(group_velo, 0, 0)
        #############################################################
        # Duration
        group_velo.setLayout(form_time)
        self.rec_time = QLineEdit("0.5")
        self.rec_time.setFixedWidth(80)
        form_time.addRow(QLabel("Recording time (s):"), self.rec_time)
        self.trigger = QLineEdit("0.02")
        self.trigger.setFixedWidth(80)
        form_time.addRow(QLabel("Trigger sensitivity (mm/s):"), self.trigger)
        # Get list of sound devices
        self.devs = []
        self.devs_ix = []
        self.devs_rate = []
        for ix, dev in enumerate(sd.query_devices()):
            self.devs.append(dev["name"])
            self.devs_ix.append(ix)
            self.devs_rate.append(dev["default_samplerate"])

        self.cbox_dev = QComboBox()
        for dev_i in self.devs:
            self.cbox_dev.addItem(dev_i)

        self.cbox_dev.setFixedWidth(100)
        form_time.addRow(QLabel("Device:"), self.cbox_dev)

        self.start = QPushButton("Start")
        self.start.clicked.connect(self.listen_for_signal)
        self.preview = QPushButton("Preview")
        self.preview.clicked.connect(self.start_live_recording)
        form_time.addRow(self.start, self.preview)

        #############################################################
        # Board properties
        group_board = QGroupBox("Board properties")
        form_board = QFormLayout()
        # form_board.addStretch()
        grid.addWidget(group_board, 0, 1)
        group_board.setLayout(form_board)

        self.board_w = QLineEdit("100")
        self.board_t = QLineEdit("30")
        self.board_l = QLineEdit("1000")
        self.board_kg = QLineEdit("1.0")
        self.board_w.setFixedWidth(100)
        self.board_t.setFixedWidth(100)
        self.board_l.setFixedWidth(100)
        self.board_kg.setFixedWidth(100)
        form_board.addRow(QLabel("Width (mm):"), self.board_w)
        form_board.addRow(QLabel("Thickness (mm):"), self.board_t)
        form_board.addRow(QLabel("Length (mm):"), self.board_l)
        form_board.addRow(QLabel("Weight (kg):"), self.board_kg)

        #############################################################
        # Frequency region
        group_freq = QGroupBox("Frequency range")
        # layout_freq =
        grid_freq = QGridLayout()
        group_freq.setLayout(grid_freq)
        grid.addWidget(group_freq, 2, 0, 1, 1)

        self.freq_min_slide = QSlider(QtCore.Qt.Horizontal)
        self.freq_max_slide = QSlider(QtCore.Qt.Horizontal)
        self.min_freq = QLineEdit("50")
        self.max_freq = QLineEdit("20000")
        self.freq_max_slide.setValue(99)

        self.freq_min_slide.sliderMoved[int].connect(self.update_min_freq)
        self.freq_max_slide.sliderMoved[int].connect(self.update_max_freq)
        self.min_freq.textEdited.connect(self.update_min_freq_val)
        self.max_freq.textEdited.connect(self.update_max_freq_val)

        grid_freq.addWidget(QLabel("Min freq. (Hz):"), 0, 0)
        grid_freq.addWidget(QLabel("Max freq. (Hz):"), 2, 0)
        grid_freq.addWidget(self.min_freq, 0, 1)
        grid_freq.addWidget(self.max_freq, 2, 1)
        grid_freq.addWidget(self.freq_min_slide, 1, 0, 1, 2)
        grid_freq.addWidget(self.freq_max_slide, 3, 0, 1, 2)

        #############################################################
        # Results
        self.results = QTableWidget()
        self.results.setColumnCount(2)
        self.results.setRowCount(5)
        header = self.results.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.results.setHorizontalHeaderLabels(["Freq. [Hz]", "E_dyn [MPa]"])
        grid.addWidget(self.results)

        #############################################################
        # Matplotlib
        self.canvas = MplCanvas(self.main_widget, width=5, height=2, dpi=100)
        self.canvas_f = MplCanvas(self.main_widget, width=5, height=2, dpi=100)

        self.init_plots()

        grid.addWidget(self.canvas, 3, 0, 1, 2)
        grid.addWidget(self.canvas_f, 4, 0, 1, 2)

        self.main_widget.setFocus()
        self.setCentralWidget(self.main_widget)

        self.show()

    def update_min_freq(self, val):
        freq = val * 20000.0 / 99.0
        self.min_freq.setText(f"{freq:1.0f}")

    def update_max_freq(self, val):
        freq = val * 20000.0 / 99.0
        self.max_freq.setText(f"{freq:1.0f}")

    def update_min_freq_val(self, val):
        freq = float(val) * 99.0 / 20000.0
        self.freq_min_slide.setValue(freq)

    def update_max_freq_val(self, val):
        freq = float(val) * 99.0 / 20000.0
        self.freq_max_slide.setValue(freq)

    def listen_for_signal(self):
        self.preview.setEnabled(False)
        worker = Worker(self._listen_for_signal)
        self.threadpool.start(worker)

    def _listen_for_signal(self):
        dev_sel = self.cbox_dev.currentText()
        ix_sel = self.devs.index(dev_sel)
        dev_num = self.devs_ix[ix_sel]
        dev_rate = self.devs_rate[ix_sel]

        rec_time = float(self.rec_time.text())

        self.statusBar().showMessage('Waiting for impulse...')
        thress = float(self.trigger.text())
        velo = float(self.cbox_vel.currentText())

        vib_analysis = SignalAnalysis(device=dev_num, sample_rate=dev_rate, velo=velo)
        # Record signal after impulse
        vib_analysis.wait_and_record(duration=rec_time, total_recording=10, thress=thress)

        max_freq = int(self.max_freq.text())
        min_freq = int(self.min_freq.text())

        freq = vib_analysis.compute_frequencies(min_freq=min_freq, max_freq=max_freq)

        l = float(self.board_l.text())
        w = float(self.board_w.text())
        t = float(self.board_t.text())
        kg = float(self.board_kg.text())

        moes = vib_analysis.calc_moe(length=l, width=w, thick=t, weight=kg)

        for k, val in enumerate(freq):
            self.results.setItem(k, 0, QTableWidgetItem(f"{val:1.0f}"))

        for k, val in enumerate(moes):
            self.results.setItem(k, 1, QTableWidgetItem(f"{val:1.0f}"))

        vib_analysis.make_plot_gui(self.canvas.axes, self.canvas_f.axes)
        # gui.status = "Idle..."
        self.statusBar().showMessage('Ready')
        self.preview.setEnabled(True)

    def start_live_recording(self):
        """Start live plotting of signal."""
        self.preview.setText("Stop")
        self.preview.clicked.connect(self.stop_live_preview)

        dev_sel = self.cbox_dev.currentText()
        ix_sel = self.devs.index(dev_sel)
        dev_num = self.devs_ix[ix_sel]
        dev_rate = int(self.devs_rate[ix_sel])

        self.statusBar().showMessage('Preview...')
        fs = int(dev_rate)
        rec_time = 5
        self.downsample = 10

        # Plot
        length = int(rec_time * fs / (self.downsample))
        self.live_data = np.zeros((length, 1))
        self.time = np.arange(start=0, step=float(self.downsample) / float(fs),
                              stop=rec_time)

        ax = self.canvas.axes
        self.lines = ax.plot(self.live_data, color="C0", lw=0.7)

        ax.axis((0, len(self.live_data), -1, 1))
        ax.grid(True)

        self.stream = sd.InputStream(device=dev_num, channels=1, samplerate=fs,
                                     callback=self.audio_callback)

        with self.stream:
            self.ani = FuncAnimation(self.canvas.figure, self.update_live_preview,
                                     interval=100, blit=True, repeat=False)

    def stop_live_preview(self):
        self.ani.event_source.stop()
        # self.stream.stop()
        self.stream.close()
        self.preview.setText("Preview")
        self.preview.clicked.connect(self.start_live_recording)
        self.statusBar().showMessage('Ready...')

    def update_live_preview(self, frame):
        while True:
            try:
                data = q.get_nowait()
            except queue.Empty:
                break
            shift = len(data)
            self.live_data = np.roll(self.live_data, -shift, axis=0)
            self.live_data[-shift:, :] = data
        for column, line in enumerate(self.lines):
            line.set_ydata(self.live_data[:, column])
        return self.lines

    def init_plots(self):
        """
        Initialize plots.
        """
        ax1 = self.canvas.axes
        ax2 = self.canvas_f.axes

        ax1.set_xlabel("Time [s]")
        ax1.set_ylabel("Velocity [mm/s]")

        ax2.set_xlabel("Frequency [Hz]")
        ax2.set_ylabel("PSD")

        self.canvas.figure.tight_layout()
        self.canvas_f.figure.tight_layout()

        self.canvas.draw()
        self.canvas_f.draw()

    def audio_callback(self, indata, frames, time, status):
        """This is called (from a separate thread) for each audio block."""
        if status:
            print(status, file=sys.stderr)
        # Fancy indexing with mapping creates a (necessary!) copy:
        q.put(indata[::self.downsample, mapping])


class Worker(QRunnable):
    """
    Worker Thread.

    Used to not block the GUI while aquiring data.

    """
    def __init__(self, fn, *args, **kwargs):
        super(Worker, self).__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs

    @pyqtSlot()
    def run(self):
        self.fn()


class MplCanvas(FigureCanvas, FuncAnimation):
    """Ultimately, this is a QWidget (as well as a FigureCanvasAgg, etc.)."""
    def __init__(self, parent=None, width=5, height=4, dpi=100):
        fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = fig.add_subplot(111)

        self.compute_initial_figure()

        FigureCanvas.__init__(self, fig)
        self.setParent(parent)

        FigureCanvas.setSizePolicy(self, QtWidgets.QSizePolicy.Expanding,
                                   QtWidgets.QSizePolicy.Expanding)
        FigureCanvas.updateGeometry(self)

    def compute_initial_figure(self):
        pass


if __name__ == "__main__":
    app = QApplication([])
    window = Window()
    app.exec_()
