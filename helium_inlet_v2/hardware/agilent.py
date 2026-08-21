'''
This script contains the functions needed to communicate and interact with the Agilent 34970A,
including specific pressure conversion matrices for the instrument's vacuum gauges.
'''

import serial
import math
import time
from config import (
    AGILENT_PORT,
    AGILENT_BAUD,
    TC_CHANNELS,
    VOLT_CHANNELS,
    VALVE_SLOT_PREFIX,
    VALVE_CHANNELS,
    STATE_VALVE_MAP,
)


class Agilent34970A:
    def __init__(self):
        self.device = None
        self.connected = False

    def connect(self):
        try:
            self.device = serial.Serial(
                port=AGILENT_PORT,
                baudrate=AGILENT_BAUD,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=2.0,
            )
            self.device.reset_input_buffer()
            self.device.reset_output_buffer()
            self.device.write(b"*CLS\r\n")
            self.device.write(b"*IDN?\r\n")
            time.sleep(0.1)
            idn = self.device.readline().decode("utf-8", errors="ignore").strip()
            self.connected = bool(idn)
            return idn
        except Exception:
            self.connected = False
            return None

    def read_all(self):
        if not self.connected or not self.device:
            return None, None

        try:
            self.device.reset_input_buffer()

            # Read Thermocouples
            self.device.write(f"MEASure:TEMPerature? TC,T,DEF,(@{TC_CHANNELS})\r\n".encode("utf-8"))
            time.sleep(0.1)
            raw_tc = self.device.readline().decode("utf-8", errors="ignore").strip()

            # Read Voltages
            self.device.write(f"MEASure:VOLTage:DC? AUTO,DEF,(@{VOLT_CHANNELS})\r\n".encode("utf-8"))
            time.sleep(0.1)
            raw_volt = self.device.readline().decode("utf-8", errors="ignore").strip()

            tc_vals = [float(x) for x in raw_tc.split(",") if x.strip()] if raw_tc else []
            v_vals = [float(x) for x in raw_volt.split(",") if x.strip()] if raw_volt else []
            return tc_vals, v_vals
        except Exception:
            self.connected = False
            return None, None

    def set_flow_state(self, state_num: int) -> bool:
        """Sends clean OPEN/CLOSE commands to relays without buffer-clogging queries."""
        if not self.connected or not self.device:
            return False

        if state_num not in STATE_VALVE_MAP:
            return False

        active_valves = STATE_VALVE_MAP[state_num]

        # Enforce exact 3-digit channel syntax (e.g., "101", "102")
        all_channels = {
            v: f"{int(VALVE_SLOT_PREFIX)}{int(ch):02d}"
            for v, ch in VALVE_CHANNELS.items()
        }

        close_list = [all_channels[v] for v in active_valves if v in all_channels]
        open_list = [ch for ch in all_channels.values() if ch not in close_list]

        try:
            self.device.reset_input_buffer()

            # 1. Open unused relay channels (Depressurize)
            if open_list:
                open_str = ",".join(open_list)
                self.device.write(f"ROUTe:OPEn (@{open_str})\r\n".encode("utf-8"))
                time.sleep(0.1)

            # 2. Close active relay channels (Pressurize)
            if close_list:
                close_str = ",".join(close_list)
                self.device.write(f"ROUTe:CLOSe (@{close_str})\r\n".encode("utf-8"))
                time.sleep(0.1)

            return True
        except Exception as e:
            print(f"[Agilent Hardware Error] set_flow_state failed: {e}")
            self.connected = False
            return False

    def emergency_stop(self) -> bool:
        """Opens all relay channels immediately."""
        if not self.connected or not self.device:
            return False

        all_channels = [
            f"{int(VALVE_SLOT_PREFIX)}{int(ch):02d}" for ch in VALVE_CHANNELS.values()
        ]
        ch_str = ",".join(all_channels)
        try:
            self.device.write(f"ROUTe:OPEn (@{ch_str})\r\n".encode("utf-8"))
            return True
        except Exception:
            self.connected = False
            return False

    @staticmethod
    def format_temp(val):
        if val is None: return "---.-- °C"
        if val > 9e9: return "OPEN / NC"
        return f"{val:.2f} °C"

    @staticmethod
    def format_voltage(volts):
        if volts is None: return "---.-- V"
        return f"{volts:.2f} V"

    @staticmethod
    def calc_chamber_aim_sl_pressure(volts):
        if volts is None: return None, "---.--- Torr"
        if volts < 2.00: return 7.5e-9, "< 7.5e-09 Torr"
        if volts > 10.00: return 7.5e-3, "> 7.5e-03 Torr"
        
        aim_sl_table_torr = [
            (2.00, 7.5e-9), (2.50, 1.8e-8), (3.00, 4.4e-8), (3.20, 6.1e-8),
            (3.40, 8.3e-8), (3.60, 1.1e-7), (3.80, 1.6e-7), (4.00, 2.2e-7),
            (4.20, 3.0e-7), (4.40, 4.1e-7), (4.60, 5.5e-7), (4.80, 7.4e-7),
            (5.00, 9.8e-7), (5.20, 1.3e-6), (5.40, 1.7e-6), (5.60, 2.1e-6),
            (5.80, 2.7e-6), (6.00, 3.4e-6), (6.20, 4.2e-6), (6.40, 5.2e-6),
            (6.60, 6.3e-6), (6.80, 7.5e-6), (7.00, 9.0e-6), (7.20, 1.1e-5),
            (7.40, 1.3e-5), (7.60, 1.5e-5), (7.80, 1.8e-5), (8.00, 2.2e-5),
            (8.20, 2.6e-5), (8.40, 3.2e-5), (8.60, 4.3e-5), (8.80, 5.9e-5),
            (9.00, 9.0e-5), (9.20, 1.4e-4), (9.40, 2.5e-4), (9.60, 5.0e-4),
            (9.80, 1.3e-3), (9.90, 2.7e-3), (10.00, 7.5e-3)
        ]
        for v, p in aim_sl_table_torr:
            if abs(volts - v) < 0.001: return p, f"{p:.2e} Torr"
        for i in range(len(aim_sl_table_torr) - 1):
            v1, p1 = aim_sl_table_torr[i]
            v2, p2 = aim_sl_table_torr[i + 1]
            if v1 < volts < v2:
                log_p = math.log10(p1) + (volts - v1) * ((math.log10(p2) - math.log10(p1)) / (v2 - v1))
                pressure = 10**log_p
                return pressure, f"{pressure:.2e} Torr"
        return None, "Error"

    @staticmethod
    def calc_trap_penning_pressure(volts):
        if volts is None or volts < 0.5: return None, "---.--- Torr"
        try:
            pressure_torr = (10 ** ((volts * 0.875) - 10.75)) * 0.750062
            return pressure_torr, f"{pressure_torr:.2e} Torr"
        except Exception: return None, "Error"

    @staticmethod
    def calc_convectron_375_pressure(volts):
        if volts is None: return None, "---.--- Torr"
        if volts < 0.0: return 1.0e-4, "< 1.00e-04 Torr"
        if volts > 7.1: return 1000.0, "> 1000 Torr"
        try:
            pressure_torr = 10 ** (volts - 4)
            return pressure_torr, f"{pressure_torr:.2e} Torr"
        except Exception: return None, "Error"