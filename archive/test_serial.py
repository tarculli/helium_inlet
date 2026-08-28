import serial
import time

# --- CONFIGURATION ---
SERIAL_PORT = '/dev/ttyUSB0'
BAUD_RATE = 57600
CHANNEL = '102'
TC_TYPE = 'T' # Options: K, J, T, E, N, R, S, B

print(f"Connecting to Keysight 34970A on {SERIAL_PORT}...")

try:
    ser = serial.Serial(
        port=SERIAL_PORT,
        baudrate=BAUD_RATE,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        xonxoff=True,          # Flow control matching panel
        timeout=3.0
    )

    ser.reset_input_buffer()
    ser.reset_output_buffer()

    # 1. Clear status
    ser.write(b"*CLS\r\n")
    time.sleep(0.1)

    # 2. Configure Channel 102 for Thermocouple temperature reading (°C)
    config_cmd = f"CONF:TEMP TC,{TC_TYPE},(@{CHANNEL})\r\n"
    ser.write(config_cmd.encode('utf-8'))
    time.sleep(0.2)

    print(f"Reading Type-{TC_TYPE} Thermocouple on Channel {CHANNEL}...\n")
    print("Press Ctrl+C to stop.")
    print("-" * 35)

    # 3. Reading Loop
    while True:
        # Request a reading
        ser.write(b"READ?\r\n")
        raw_val = ser.readline().decode('utf-8', errors='ignore').strip()

        if raw_val:
            try:
                temp_c = float(raw_val)
                temp_f = (temp_c * 9/5) + 32
                timestamp = time.strftime("%H:%M:%S")
                print(f"[{timestamp}] Temp: {temp_c:.2f} °C  ({temp_f:.2f} °F)")
            except ValueError:
                print(f"Raw Output: {raw_val}")
        else:
            print("⚠️ Timeout: No data received.")

        time.sleep(1.0)

except serial.SerialException as e:
    print(f"\n❌ Serial Port Error: {e}")
except KeyboardInterrupt:
    print("\nExiting script. Goodbye!")
finally:
    if 'ser' in locals() and ser.is_open:
        ser.close()