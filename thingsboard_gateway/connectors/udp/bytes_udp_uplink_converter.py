#     Copyright 2021. ThingsBoard
#
#     Licensed under the Apache License, Version 2.0 (the "License");
#     you may not use this file except in compliance with the License.
#     You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#     Unless required by applicable law or agreed to in writing, software
#     distributed under the License is distributed on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#     See the License for the specific language governing permissions and
#     limitations under the License.

from pymodbus.constants import Endian
from pymodbus.exceptions import ModbusIOException
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.pdu import ExceptionResponse

from connectors.udp.udp_converter import UDPConverter, log

HEX = "0x"

class BytesUDPUplinkConverter(UDPConverter):
    def __init__(self, config):
        self.__datatypes = {
            "timeseries": "telemetry",
            "attributes": "attributes"
            }
        self.__result = {"deviceName": config.get("deviceName", "UdpDevice %s" % (str(config["unitId"]))),
                         "deviceType": config.get("deviceType", "default")}

    def convert(self, config, data):
        
        self.__result["telemetry"] = []
        self.__result["attributes"] = []
        for config_data in data:
            for tag in data[config_data]:
                try:
                    configuration = data[config_data][tag]["data_sent"]
                    response = data[config_data][tag]["input_data"]

                    for key_data in configuration["values"]:
                        key = key_data["tag"]
                        values = None
                        result = None

                        nodeId = int(HEX + response[0:4], 0)
                        DLC = int(HEX + response[4:6], 0)
                        dataFrame = response[6:len(response)]
                        data_length = key_data["length"] if key_data["length"] != -1 else len(dataFrame) - key_data["start"]
                        if nodeId == int(configuration["nodeId"]):
                            # The 'value' variable is used in eval
                            if key_data["type"][0] == "b":
                                data_to_bin = bin(int(hex(int(HEX +dataFrame,0)),16))[2:].zfill(64)
                                values = data_to_bin[int(key_data["start"]) : int(key_data["start"]) + int(data_length)]
                                
                            elif key_data["type"][0] == "i" or key_data["type"][0] == "l":
                                values = int(HEX + dataFrame[int(key_data["start"]) * 2:int(key_data["start"])*2 + int(data_length)*2], 0)
                            
                            if values is not None:
                                if key_data.get("expression", ""):
                                    result = eval(key_data["expression"],
                                                                {"__builtins__": {}} if True else globals(),
                                                                {"value": values, "can_data": dataFrame})
                                else:
                                    result = values                            
                            
                        if result is not None:
                            self.__result[self.__datatypes[config_data]].append({key: result})

                except Exception as e:
                    log.exception(e)
        log.debug(self.__result)
        return self.__result
