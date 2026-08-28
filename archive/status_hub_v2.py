import math
import customtkinter as ctk
import serial
import threading
import time
from collections import deque

# Matplotlib Imports for Tkinter
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# CustomTkinter Theme Settings
ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("blue")

def calc_aim_sl_pressure(volts):
    """Calculates Chamber pressure (mbar) for Edwards AIM-SL Gauge (returns float)."""
    if volts is None or volts < 2.00: return 1.0e-8
    if volts > 10.00: return 1.0e-2

    aim_sl_table = [
        (2.00, 1.0e-8), (2.50, 2.4e-8), (3.00, 5.8e-8), (3.20, 8.1e-8),
        (3.40, 1.1e-7), (3.60, 1.5e-7), (3.80, 2.1e-7), (4.00, 2.9e-7),
        (4.20, 4.0e-7), (4.40, 5.4e-7), (4.60, 7.3e-7), (4.80, 9.8e-7),
        (5.00, 1.3e-6), (5.20, 1.7e-6), (5.40, 2.2e-6), (5.60, 2.8e-6),
        (5.80, 3.6e-6), (6.00, 4.5e-6), (6.20, 5.6e-6), (6.40, 6.9e-6),
        (6.60, 8.4e-6), (6.80, 1.0e-5), (7.00, 1.2e-5), (7.20, 1.4e-5),
        (7.40, 1.7e-5), (7.60, 2.0e-5), (7.80, 2.4e-5), (8.00, 2.9e-5),
        (8.20, 3.5e-5), (8.40, 4.3e-5), (8.60, 5.7e-5), (8.80, 7.9e-5),
        (9.00, 1.2e-4), (9.20, 1.9e-4), (9.40, 3.3e-4), (9.60, 6.7e-4),
        (9.80, 1.7e-3), (9.90, 3.6e-3), (10.00, 1.0e-2)
    ]

    for v, p in aim_sl_table:
        if abs(volts - v) < 0.001:
            return p

    for i in range(len(aim_sl_table) - 1):
        v1, p1 = aim_sl_table[i]
        v2, p2 = aim_sl_table[i+1]
        
        if v1 < volts < v2:
            log_p1 = math.log10(p1)
            log_p2 = math.log10(p2)
            log_p = log_p1 + (volts - v1) * ((log_p2 - log_p1) / (v2 - v1))
            return 10 ** log_p
    return 1.0e-8


def calc_trap_penning_pressure(volts):
    """Calculates Trap Penning B pressure (returns float)."""
    if volts is None: return 1.0e-8
    try:
        return 10 ** ((volts * 0.875) - 10.75)
    except Exception:
        return 1.0e-8


class StatusHubApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Window Configuration
        self.title("Inlet Control Hub")
        self.geometry("900x700")
        self.resizable(True, True)

        # Buffer for Plotting (60 seconds of data)
        self.max_points = 60
        self.plot_p115 = deque([None]*self.max_points, maxlen=self.max_points)
        self.plot_p116 = deque([None]*self.max_points, maxlen=self.max_points)
        
        # Thread-safe holding variables for the GUI to pull from
        self.current_p115 = None
        self.current_p116 = None

        # --- UI LAYOUT ---
        self.header = ctk.CTkLabel(self, text="AGILENT 34970A MONITOR", font=("Arial", 16, "bold"))
        self.header.pack(pady=(15, 2))

        self.status_label = ctk.CTkLabel(self, text="● Initializing...", text_color="orange", font=("Arial", 12))
        self.status_label.pack(pady=2)

        # Cards Container
        self.cards_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.cards_frame.pack(pady=15, padx=20, fill="x")

        # --- Chamber Pressure (CH 115) ---
        self.card_chamber = ctk.CTkFrame(self.cards_frame, height=130, corner_radius=10)
        self.card_chamber.pack_propagate(False)
        self.card_chamber.pack(side="left", padx=10, expand=True, fill="x")
        ctk.CTkLabel(self.card_chamber, text="CHAMBER (115 AIM-SL)", font=("Arial", 11, "bold"), text_color="gray").pack(pady=(15, 0))
        self.val_115_label = ctk.CTkLabel(self.card_chamber, text="---.--- mbar", font=("Arial", 22, "bold"))
        self.val_115_label.pack(pady=(15, 0))

        # --- Trap Pressure (CH 116) ---
        self.card_trap = ctk.CTkFrame(self.cards_frame, height=130, corner_radius=10)
        self.card_trap.pack_propagate(False)
        self.card_trap.pack(side="left", padx=10, expand=True, fill="x")
        ctk.CTkLabel(self.card_trap, text="TRAP (116 PENNING)", font=("Arial", 11, "bold"), text_color="gray").pack(pady=(15, 0))
        self.val_116_label = ctk.CTkLabel(self.card_trap, text="---.--- mbar", font=("Arial", 22, "bold"))
        self.val_116_label.pack(pady=(15, 0))

        # --- PV Temp (CH 102) ---
        self.card_t = ctk.CTkFrame(self.cards_frame, height=130, corner_radius=10)
        self.card_t.pack_propagate(False)
        self.card_t.pack(side="left", padx=10, expand=True, fill="x")
        ctk.CTkLabel(self.card_t, text="PV TEMP (102)", font=("Arial", 11, "bold"), text_color="gray").pack(pady=(15, 0))
        self.t_value_label = ctk.CTkLabel(self.card_t, text="---.-- °C", font=("Arial", 22, "bold"))
        self.t_value_label.pack(pady=(15, 0))

        # --- LIVE MATPLOTLIB CHART ---
        self.plot_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.plot_frame.pack(padx=25, pady=5, fill="both", expand=True)

        self.fig, self.ax = plt.subplots(figsize=(8, 3), dpi=100)
        self.fig.patch.set_facecolor('#f3f4f6') # Match light theme background
        self.ax.set_facecolor('#ffffff')
        
        # Logarithmic configuration
        self.ax.set_yscale('log')
        self.ax.set_ylim(1e-8, 1e-2)
        self.ax.set_title("Live Vacuum System Pressures (mbar)", fontsize=10, color="#4b5563", pad=10)
        self.ax.grid(True, which="both", ls="--", linewidth=0.5, color='#e5e7eb')

        # Initialize line objects
        self.line_115, = self.ax.plot([], [], label="Chamber (115)", color="#2563eb", linewidth=2)
        self.line_116, = self.ax.plot([], [], label="Trap (116)", color="#d97706", linewidth=2)
        self.ax.legend(loc="upper right", fontsize=8)

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        # Footer
        self.time_label = ctk.CTkLabel(self, text="Last Update: Waiting for data...", font=("Arial", 11), text_color="gray")
        self.time_label.pack(pady=(5, 2))
        self.idn_label = ctk.CTkLabel(self, text="Device: Disconnected", font=("Arial", 10), text_color="darkgray")
        self.idn_label.pack(pady=(0, 10))

        # --- START PROCESSES ---
        threading.Thread(target=self.serial_hardware_loop, daemon=True).start()
        self.update_gui_plot_loop() # Start the Tkinter after() loop

    def update_gui_plot_loop(self):
        """Main thread loop to safely pull data and update the plot."""
        # Append latest data
        self.plot_p115.append(self.current_p115)
        self.plot_p116.append(self.current_p116)

        # Prepare X and Y arrays (filtering out None values)
        x_data = list(range(self.max_points))
        
        y_115 = [val if val is not None else float('nan') for val in self.plot_p115]
        y_116 = [val if val is not None else float('nan') for val in self.plot_p116]

        self.line_115.set_data(x_data, y_115)
        self.line_116.set_data(x_data, y_116)
        
        self.ax.set_xlim(0, self.max_points - 1)
        self.canvas.draw_idle()

        # Reschedule next update in 1 second
        self.after(1000, self.update_gui_plot_loop)


    def serial_hardware_loop(self):
        """Continuous background thread handling hardware communication."""
        SERIAL_PORT = "/dev/ttyUSB0"
        BAUD_RATE = 57600
        TC_CHANNEL = "102"
        VOLT_CHANNELS = "115,116"

        while True:
            device = None
            try:
                self.update_status("● Connecting to hardware...", "orange")

                device = serial.Serial(
                    port=SERIAL_PORT, baudrate=BAUD_RATE, bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                    xonxoff=True, rtscts=False, dsrdtr=False, timeout=3.0,
                )

                device.reset_input_buffer()
                device.reset_output_buffer()

                device.write(b"*CLS\r\n")
                time.sleep(0.1)
                device.write(b"*IDN?\r\n")
                time.sleep(0.2)
                idn_response = device.readline().decode("utf-8", errors="ignore").strip()

                if idn_response:
                    self.update_idn(f"Device: {idn_response}")
                    self.update_status("● Connected & Streaming", "#2ea043")
                else:
                    self.update_idn("Device: Unknown")
                    self.update_status("● Connected (No ID response)", "orange")

                while True:
                    loop_start = time.time()

                    # 1. Query Pressures (Voltages 115, 116)
                    device.write(f"MEASure:VOLTage:DC? AUTO,DEF,(@{VOLT_CHANNELS})\r\n".encode("utf-8"))
                    raw_volt = device.readline().decode("utf-8", errors="ignore").strip()
                    
                    # 2. Query Channel 102 Temperature (Type-T)
                    device.write(f"MEASure:TEMPerature? TC,T,DEF,(@{TC_CHANNEL})\r\n".encode("utf-8"))
                    raw_temp = device.readline().decode("utf-8", errors="ignore").strip()

                    timestamp = time.strftime("%H:%M:%S")

                    # Parse Voltages
                    p115_str, p116_str = "---.--- mbar", "---.--- mbar"
                    
                    if raw_volt:
                        v_parts = raw_volt.split(',')
                        if len(v_parts) == 2:
                            try:
                                v115, v116 = float(v_parts[0]), float(v_parts[1])
                                
                                # Convert & store for plotter
                                self.current_p115 = calc_aim_sl_pressure(v115)
                                self.current_p116 = calc_trap_penning_pressure(v116)

                                # Format text
                                p115_str = f"{self.current_p115:.2e} mbar"
                                p116_str = f"{self.current_p116:.2e} mbar"
                            except ValueError:
                                pass

                    # Parse Temperature
                    t_str = "---.-- °C"
                    if raw_temp:
                        try:
                            temp_c = float(raw_temp)
                            t_str = "OPEN / NC" if temp_c > 9e9 else f"{temp_c:.2f} °C"
                        except ValueError:
                            t_str = f"{raw_temp}"

                    # Send to GUI Text labels
                    self.update_readouts(p115_str, p116_str, t_str, f"Last Update: {timestamp}")

                    # Enforce ~1s polling rate
                    elapsed = time.time() - loop_start
                    time.sleep(max(0.1, 1.0 - elapsed))

            except (serial.SerialException, OSError):
                self.update_status("● Connection Lost! Retrying in 3s...", "#f85149")
                self.update_readouts("---.--- mbar", "---.--- mbar", "---.-- °C", "Last Update: Serial Error")
                self.update_idn("Device: Disconnected")
                
                self.current_p115 = None
                self.current_p116 = None

                if device and device.is_open:
                    device.close()
                time.sleep(3.0)

    # --- THREAD-SAFE GUI UPDATE METHODS ---
    def update_status(self, text, color):
        self.status_label.configure(text=text, text_color=color)

    def update_idn(self, text):
        self.idn_label.configure(text=text)

    def update_readouts(self, p115, p116, t, time_text):
        self.val_115_label.configure(text=p115)
        self.val_116_label.configure(text=p116)
        self.t_value_label.configure(text=t)
        self.time_label.configure(text=time_text)


if __name__ == "__main__":
    app = StatusHubApp()
    app.mainloop()