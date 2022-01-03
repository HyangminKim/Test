#!/usr/bin/env python3

import pymodbus
from pymodbus.pdu import ModbusRequest
from pymodbus.client.sync import ModbusSerialClient as ModbusClient
from pymodbus.transaction import ModbusRtuFramer

client = ModbusClient(method='rtu', port="/dev/ttyTHS0", baudrate=9600, parity='N', timeout=0.1)
client.debug_enabled()
connection = client.connect()

while(1):
    read_vals  = client.read_input_registers(0, 1, unit=2) # start_address, count, slave_id
    print(read_vals)
    read_vals  = client.read_input_registers(1, 1, unit=2) # start_address, count, slave_id
    print(read_vals)


# write registers
# write  = client.write_register(1,425,unit=2)# address = 1, value to set = 425, slave ID = 1