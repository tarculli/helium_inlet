import time
import serial 

from config import (
    AGILENT_BAUD,
    AGILENT_PORT,
    VALVE_CHANNELS,
    VALVE_SLOT_PREFIX
)

def test_flow_paths(active_valves=None):
    """Given valve numbers, test gas flow on gas selector safely."""
    if active_valves is None:
        active_valves = ['V1']

    ser = None
    try:
        # 1. Connect to the Agilent
        ser = serial.Serial(
            port=AGILENT_PORT,
            baudrate=AGILENT_BAUD,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=2.0,
        )
        ser.reset_input_buffer()
        ser.reset_output_buffer()

        # Clear status registers and query identity
        ser.write(b"*CLS\r\n")
        ser.write(b"*IDN?\r\n")
        time.sleep(0.1)

        idn = ser.readline().decode("utf-8", errors="ignore").strip()
        if not idn:
            print("❌ Agilent mainframe did not respond to *IDN?")
            return False

        print(f"✅ Connected to: {idn}")

        # 2. Translate valve names to Agilent relay channels
        all_channels = {
            v: str(VALVE_SLOT_PREFIX + int(ch))
            for v, ch in VALVE_CHANNELS.items()
        }
        
        close_list = [all_channels[v] for v in active_valves if v in all_channels]
        open_list = [ch for ch in all_channels.values() if ch not in close_list]

        # 3. Safely toggle valve channels
        ser.reset_input_buffer()

        # Open non-active valve relays first (prevents over-pressurization)
        if open_list:
            cmd = f"ROUTe:OPEn (@{','.join(open_list)})\r\n"
            ser.write(cmd.encode("utf-8"))
            time.sleep(0.1)

        # Close active valve relays to energize selected path
        if close_list:
            cmd = f"ROUTe:CLOSe (@{','.join(close_list)})\r\n"
            ser.write(cmd.encode("utf-8"))
            time.sleep(0.1)

        print(f"✅ Flow path set successfully! Active valves: {active_valves}")
        return True

    except Exception as e:
        print(f"❌ [Agilent Hardware Error]: {e}")
        return False

    finally:
        # Always close serial connection when function finishes or fails
        if ser and ser.is_open:
            ser.close()