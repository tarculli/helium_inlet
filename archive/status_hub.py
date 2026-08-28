import math
import customtkinter as ctk
import serial
import threading
import time

# CustomTkinter Theme Settings
ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("blue")


class StatusHubApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Window Configuration
        self.title("Inlet Control Hub")
        self.geometry("580x400")
        self.resizable(True, True)

        # --- UI LAYOUT ---
        # 1. Title Header
        self.header = ctk.CTkLabel(
            self, text="AGILENT 34970A MONITOR", font=("Arial", 16, "bold")
        )
        self.header.pack(pady=(15, 2))

        # 2. Connection Status Indicator
        self.status_label = ctk.CTkLabel(
            self, text="● Initializing...", text_color="orange", font=("Arial", 12)
        )
        self.status_label.pack(pady=2)

        # 3. Channels Container (Side-by-Side Layout)
        self.cards_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.cards_frame.pack(pady=15, padx=20, fill="x")

        # --- Channel 116 (Penning B Pressure) ---
        self.card_v = ctk.CTkFrame(self.cards_frame, width=250, height=180, corner_radius=10)
        self.card_v.pack_propagate(False)
        self.card_v.pack(side="left", padx=10, expand=True)

        self.v_title = ctk.CTkLabel(
            self.card_v,
            text="CHANNEL 116 (PENNING B PRESSURE)",
            font=("Arial", 11, "bold"),
            text_color="gray",
        )
        self.v_title.pack(pady=(25, 0))

        self.v_value_label = ctk.CTkLabel(
            self.card_v, text="---.--- mbar", font=("Arial", 26, "bold")
        )
        self.v_value_label.pack(pady=(20, 0))

        # ---  Channel 102 (Thermocouple Temp) ---
        self.card_t = ctk.CTkFrame(self.cards_frame, width=250, height=180, corner_radius=10)
        self.card_t.pack_propagate(False)
        self.card_t.pack(side="right", padx=10, expand=True)

        self.t_title = ctk.CTkLabel(
            self.card_t,
            text="CHANNEL 102 (PV TC TEMP)",
            font=("Arial", 11, "bold"),
            text_color="gray",
        )
        self.t_title.pack(pady=(25, 0))

        self.t_value_c_label = ctk.CTkLabel(
            self.card_t, text="---.-- °C", font=("Arial", 28, "bold")
        )
        self.t_value_c_label.pack(pady=(20, 0))

        # 4. Footer info (Timestamp & Hardware Identity)
        self.time_label = ctk.CTkLabel(
            self, text="Last Update: Waiting for data...", font=("Arial", 11), text_color="gray"
        )
        self.time_label.pack(pady=(5, 2))

        self.idn_label = ctk.CTkLabel(
            self, text="Device: Disconnected", font=("Arial", 10), text_color="darkgray"
        )
        self.idn_label.pack(pady=(0, 10))

        # --- BACKGROUND HARDWARE WORKER ---
        threading.Thread(target=self.serial_hardware_loop, daemon=True).start()

    def serial_hardware_loop(self):
        """Continuous background thread handling hardware communication."""
        SERIAL_PORT = "/dev/ttyUSB0"
        BAUD_RATE = 57600
        TC_CHANNEL = "102"
        TC_TYPE = "T"
        VOLT_CHANNEL = "116"

        while True:
            device = None
            try:
                self.update_status("● Connecting to hardware...", "orange")

                # Serial settings matching hardware requirements
                device = serial.Serial(
                    port=SERIAL_PORT,
                    baudrate=BAUD_RATE,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    xonxoff=True,
                    rtscts=False,
                    dsrdtr=False,
                    timeout=3.0,
                )

                # Clear buffers
                device.reset_input_buffer()
                device.reset_output_buffer()

                # Clear status register and verify identity
                device.write(b"*CLS\r\n")
                time.sleep(0.1)

                device.write(b"*IDN?\r\n")
                time.sleep(0.2)
                idn_response = device.readline().decode("utf-8", errors="ignore").strip()

                if idn_response:
                    self.update_idn(f"Device: {idn_response}")
                    self.update_status("● Connected & Streaming", "#2ea043")  # Green
                else:
                    self.update_idn("Device: Unknown")
                    self.update_status("● Connected (No ID response)", "orange")

                # Active streaming loop querying both channels
                while True:
                    # 1. Query Channel 116 Voltage
                    device.write(f"MEASure:VOLTage:DC? AUTO,DEF,(@{VOLT_CHANNEL})\r\n".encode("utf-8"))
                    raw_volt = device.readline().decode("utf-8", errors="ignore").strip()

                    # 2. Query Channel 102 Temperature (Type-T)
                    device.write(f"MEASure:TEMPerature? TC,{TC_TYPE},DEF,(@{TC_CHANNEL})\r\n".encode("utf-8"))
                    raw_temp = device.readline().decode("utf-8", errors="ignore").strip()

                    timestamp = time.strftime("%H:%M:%S")

                    # Parse Voltage and convert to Pressure in mbar
                    # Formula: P = 10^( (volts * 0.875) - 10.75 )
                    p_str = "---.--- mbar"
                    if raw_volt:
                        try:
                            volts = float(raw_volt)
                            pressure_mbar = 10 ** ((volts * 0.875) - 10.75)
                            p_str = f"{pressure_mbar:.2e} mbar"
                        except ValueError:
                            p_str = f"{raw_volt} mbar"

                    # Parse Temperature Reading (°C only)
                    t_c_str = "---.-- °C"
                    if raw_temp:
                        try:
                            temp_c = float(raw_temp)
                            # Handle open circuit / unplugged thermocouple (~9.9E37)
                            if temp_c > 9e9:
                                t_c_str = "OPEN / NC"
                            else:
                                t_c_str = f"{temp_c:.2f} °C"
                        except ValueError:
                            t_c_str = f"{raw_temp}"

                    # Update GUI labels safely
                    self.update_readouts(p_str, t_c_str, f"Last Update: {timestamp}")

                    time.sleep(1.0)

            except (serial.SerialException, OSError):
                # Handle disconnection cleanly and retry
                self.update_status("● Connection Lost! Retrying in 5s...", "#f85149")  # Red
                self.update_readouts("---.--- mbar", "---.-- °C", "Last Update: Serial Error")
                self.update_idn("Device: Disconnected")

                if device and device.is_open:
                    device.close()

                time.sleep(5.0)

    # --- SAFE THREAD-TO-GUI UPDATE METHODS ---
    def update_status(self, text, color):
        self.status_label.configure(text=text, text_color=color)

    def update_idn(self, text):
        self.idn_label.configure(text=text)

    def update_readouts(self, p_val, t_c_val, time_text):
        self.v_value_label.configure(text=p_val)
        self.t_value_c_label.configure(text=t_c_val)
        self.time_label.configure(text=time_text)


if __name__ == "__main__":
    app = StatusHubApp()
    app.mainloop()