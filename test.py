import serial

serial_port = serial.Serial('/dev/ttyUSB0', 9600)
data = '1|C|1;3|DB1, R01,DB0,R00\n'
serial_port.write(data.encode())
serial_port.close()
