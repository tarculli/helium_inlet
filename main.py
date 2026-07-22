import serial
import time
import sys

SERIAL_PORT = '/dev/ttyUSB0'
BAUD_RATE = 57600

print("==============================================")
print("     KEYSIGHT 34970A TERMINAL MONITOR         ")
print("==============================================")
print(f"Target Port: {SERIAL_PORT} @ {BAUD_RATE} Baud")
print("Press Ctrl+C at any time to exit.\n")

while True:
    device = None
    try:
        print("🔄 Status: Connecting to hardware...")
        
        # Exact serial parameters that passed test_serial.py
        device = serial.Serial(
            port=SERIAL_PORT,
            baudrate=BAUD_RATE,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            xonxoff=True,          # Match XON/XOFF flow control
            rtscts=False,
            dsrdtr=False,
            timeout=3.0
        )
        
        # Clear buffers
        device.reset_input_buffer()
        device.reset_output_buffer()
        
        # Send reset/clear with \r\n line ending
        device.write(b"*CLS\r\n")
        time.sleep(0.1)
        
        # Verify identity
        device.write(b"*IDN?\r\n")
        time.sleep(0.2)
        idn_response = device.readline().decode('utf-8', errors='ignore').strip()
        print(f"✅ Connected to: {idn_response}\n")
        print("Timestamp    | Channel 116 Reading")
        print("----------------------------------")
        
        # Active streaming loop
        while True:
            # Send measurement command with proper \r\n line termination
            device.write(b"MEASure:VOLTage:DC? AUTO,DEF,(@116)\r\n")
            
            raw_data = device.readline().decode('utf-8', errors='ignore').strip()
            timestamp = time.strftime("%H:%M:%S")
            
            if raw_data:
                try:
                    formatted_val = f"{float(raw_data):.5f} V"
                except ValueError:
                    formatted_val = f"{raw_data} V"
                
                # Update line in terminal
                sys.stdout.write(f"\r[{timestamp}] | {formatted_val}      ")
                sys.stdout.flush()
            else:
                raise serial.SerialException("Timeout / Empty response")
                
            time.sleep(3.0)

    except (serial.SerialException, OSError) as e:
        print(f"\n❌ Status: Connection Lost ({e})! Retrying in 5 seconds...")
        if device and device.is_open:
            device.close()
        time.sleep(5.0)
        
    except KeyboardInterrupt:
        print("\n\nExiting monitor script. Goodbye!")
        if device and device.is_open:
            device.close()
        break