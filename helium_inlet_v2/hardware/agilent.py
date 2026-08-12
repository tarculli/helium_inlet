import serial
import math
from config import AGILENT_PORT, AGILENT_BAUD, TC_CHANNELS, VOLT_CHANNELS

class Agilent34970A:
    def __init__(self):
        self.device = None
        self.connected = False

    def connect(self):
        try:
            self.device = serial.Serial(
                port=AGILENT_PORT, baudrate=AGILENT_BAUD, 
                bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE, 
                stopbits=serial.STOPBITS_ONE, timeout=2.0
            )
            self.device.reset_input_buffer()
            self.device.reset_output_buffer()
            self.device.write(b"*CLS\r\n")
            self.device.write(b"*IDN?\r\n")
            idn = self.device.readline().decode("utf-8", errors="ignore").strip()
            self.connected = bool(idn)
            return idn
        except Exception:
            self.connected = False
            return None

    def read_all(self):
        if not self.connected:
            return None, None
        
        try:
            self.device.write(f"MEASure:TEMPerature? TC,T,DEF,(@{TC_CHANNELS})\r\n".encode("utf-8"))
            raw_tc = self.device.readline().decode("utf-8", errors="ignore").strip()
            
            self.device.write(f"MEASure:VOLTage:DC? AUTO,DEF,(@{VOLT_CHANNELS})\r\n".encode("utf-8"))
            raw_volt = self.device.readline().decode("utf-8", errors="ignore").strip()
            
            tc_vals = [float(x) if x else None for x in raw_tc.split(",")]
            v_vals = [float(x) if x else None for x in raw_volt.split(",")]
            return tc_vals, v_vals
        except Exception:
            self.connected = False
            return None, None

    # (Include calc_chamber_aim_sl_pressure, calc_trap_penning_pressure, and format_temp here as static methods)