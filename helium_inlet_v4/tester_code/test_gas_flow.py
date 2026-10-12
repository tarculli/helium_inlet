import time
import serial 

from config import (
    AGILENT_BAUD,
    AGILENT_PORT,
    VALVE_CHANNELS,
    VALVE_SLOT_PREFIX
)

def test_flow_paths(active_valves=None):
    """Given valve numbers, test gas flow safely. Pass None, [], or 'none' to close all valves."""
    
    # 1. Normalize input for "All Off" / Isolation state
    if active_valves is None or str(active_valves).lower() == 'none':
        active_valves = []
    elif isinstance(active_valves, (str, int)):
        active_valves = [active_valves]

    # Filter out explicit 'none' string literals inside list inputs (e.g. ['none'])
    active_valves = [v for v in active_valves if str(v).lower() != 'none']

    ser = None
    try:
        # Connect to the Agilent Mainframe
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
        ser.flush()
        time.sleep(0.1)

        idn = ser.readline().decode("utf-8", errors="ignore").strip()
        if not idn:
            print("❌ Agilent mainframe did not respond to *IDN?")
            return False

        print(f"✅ Connected to: {idn}")

        # 2. Build channel mapping with key normalization
        all_channels = {}
        for v, ch in VALVE_CHANNELS.items():
            ch_num = int(ch)
            if ch_num < 100:
                ch_num += int(VALVE_SLOT_PREFIX)
            
            # Allow matching by '1', 'V1', 1, etc.
            all_channels[str(v)] = str(ch_num)
            all_channels[f"V{v}"] = str(ch_num)
            if str(v).startswith("V"):
                all_channels[str(v)[1:]] = str(ch_num)

        # 3. Determine channels to energize (close relay) vs de-energize (open relay)
        close_list = []
        for req in active_valves:
            req_str = str(req)
            if req_str in all_channels:
                close_list.append(all_channels[req_str])
            else:
                print(f"⚠️ Warning: Requested valve '{req}' not found in VALVE_CHANNELS map!")

        close_list = list(dict.fromkeys(close_list))
        unique_all_channels = list(dict.fromkeys(all_channels.values()))
        open_list = [ch for ch in unique_all_channels if ch not in close_list]

        # 4. Execute Hardware Relay Commands
        ser.reset_input_buffer()

        # Open non-active valve relays (de-energizes solenoids, stops airflow)
        if open_list:
            cmd = f"ROUTe:OPEn (@{','.join(open_list)})\r\n"
            ser.write(cmd.encode("utf-8"))
            ser.flush()
            time.sleep(0.1)

        # Close active valve relays (energizes selected solenoids)
        if close_list:
            cmd = f"ROUTe:CLOSe (@{','.join(close_list)})\r\n"
            ser.write(cmd.encode("utf-8"))
            ser.flush()
            time.sleep(0.1)

        # 5. Check Agilent error queue
        ser.write(b"SYSTem:ERRor?\r\n")
        ser.flush()
        time.sleep(0.1)
        err_msg = ser.readline().decode("utf-8", errors="ignore").strip()
        
        if err_msg and not err_msg.startswith("+0"):
            print(f"⚠️ Agilent SCPI Error Queue: {err_msg}")
        
        if not close_list:
            print("🛑 ALL VALVES CLOSED / DE-ENERGIZED (Gas flow isolated).")
        else:
            print(f"✅ Flow path configured! Energized channels: {close_list}")
            
        return True

    except Exception as e:
        print(f"❌ [Agilent Hardware Error]: {e}")
        return False

    finally:
        if ser and ser.is_open:
            try:
                ser.flush()
            except Exception:
                pass
            ser.close()

if __name__ == "__main__":
    # Test 1: Turn off all valves
    print("\n--- Testing All Off ---")
    test_flow_paths(None)

    # Test 2: Activate Valve 1
    # print("\n--- Testing Valve 1 ---")
    # test_flow_paths(['V1'])