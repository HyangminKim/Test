import socket
import select
import serial
import time
import ssl
import sys
from functools import partial
from pymodbus.constants import Defaults
from pymodbus.utilities import hexlify_packets, ModbusTransactionState
from pymodbus.factory import ClientDecoder
from pymodbus.exceptions import NotImplementedException, ParameterException
from pymodbus.exceptions import ConnectionException
from pymodbus.transaction import FifoTransactionManager
from pymodbus.transaction import DictTransactionManager
from pymodbus.transaction import ModbusSocketFramer, ModbusBinaryFramer
from pymodbus.transaction import ModbusAsciiFramer, ModbusRtuFramer
from pymodbus.transaction import ModbusTlsFramer
from pymodbus.client.common import ModbusClientMixin

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
import logging
_logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# The Synchronous Clients
# --------------------------------------------------------------------------- #


class BaseModbusClient(ModbusClientMixin):
    """
    Inteface for a modbus synchronous client. Defined here are all the
    methods for performing the related request methods.  Derived classes
    simply need to implement the transport methods and set the correct
    framer.
    """
    def __init__(self, framer, **kwargs):
        """ Initialize a client instance

        :param framer: The modbus framer implementation to use
        """
        self.framer = framer
        self.transaction = DictTransactionManager(self, **kwargs)
        self._debug = False
        self._debugfd = None
        self.broadcast_enable = kwargs.get('broadcast_enable', Defaults.broadcast_enable)

    # ----------------------------------------------------------------------- #
    # Client interface
    # ----------------------------------------------------------------------- #
    def connect(self):
        """ Connect to the modbus remote host

        :returns: True if connection succeeded, False otherwise
        """
        raise NotImplementedException("Method not implemented by derived class")

    def close(self):
        """ Closes the underlying socket connection
        """
        pass

    def is_socket_open(self):
        """
        Check whether the underlying socket/serial is open or not.

        :returns: True if socket/serial is open, False otherwise
        """
        raise NotImplementedException(
            "is_socket_open() not implemented by {}".format(self.__str__())
        )

    def send(self, request):
        if self.state != ModbusTransactionState.RETRYING:
            _logger.debug("New Transaction state 'SENDING'")
            self.state = ModbusTransactionState.SENDING
        return self._send(request)

    def _send(self, request):
        """ Sends data on the underlying socket

        :param request: The encoded request to send
        :return: The number of bytes written
        """
        raise NotImplementedException("Method not implemented by derived class")

    def recv(self, size):
        return self._recv(size)

    def _recv(self, size):
        """ Reads data from the underlying descriptor

        :param size: The number of bytes to read
        :return: The bytes read
        """
        raise NotImplementedException("Method not implemented by derived class")

    # ----------------------------------------------------------------------- #
    # Modbus client methods
    # ----------------------------------------------------------------------- #
    def execute(self, request=None):
        """
        :param request: The request to process
        :returns: The result of the request execution
        """
        if not self.connect():
            raise ConnectionException("Failed to connect[%s]" % (self.__str__()))
        return self.transaction.execute(request)

    # ----------------------------------------------------------------------- #
    # The magic methods
    # ----------------------------------------------------------------------- #
    def __enter__(self):
        """ Implement the client with enter block

        :returns: The current instance of the client
        """
        if not self.connect():
            raise ConnectionException("Failed to connect[%s]" % (self.__str__()))
        return self

    def __exit__(self, klass, value, traceback):
        """ Implement the client with exit block """
        self.close()

    def idle_time(self):
        """
        Bus Idle Time to initiate next transaction
        :return: time stamp
        """
        if self.last_frame_end is None or self.silent_interval is None:
            return 0
        return self.last_frame_end + self.silent_interval

    def debug_enabled(self):
        """
        Returns a boolean indicating if debug is enabled.
        """
        return self._debug

    def set_debug(self, debug):
        """
        Sets the current debug flag.
        """
        self._debug = debug

    def trace(self, writeable):
        if writeable:
            self.set_debug(True)
        self._debugfd = writeable

    def _dump(self, data, direction):
        fd = self._debugfd if self._debugfd else sys.stdout
        try:
            fd.write(hexlify_packets(data))
        except Exception as e:
            _logger.debug(hexlify_packets(data))
            _logger.exception(e)

    def register(self, function):
        """
        Registers a function and sub function class with the decoder
        :param function: Custom function class to register
        :return:
        """
        self.framer.decoder.register(function)

    def __str__(self):
        """ Builds a string representation of the connection

        :returns: The string representation
        """
        return "Null Transport"

# --------------------------------------------------------------------------- #
# Modbus UDP Client Transport Implementation
# --------------------------------------------------------------------------- #


class ModbusUdpClient(BaseModbusClient):
    """ Implementation of a modbus udp client
    """

    def __init__(self, host='127.0.0.1', port=Defaults.Port,
                 framer=ModbusSocketFramer, **kwargs):
        """ Initialize a client instance

        :param host: The host to connect to (default 127.0.0.1)
        :param port: The modbus port to connect to (default 502)
        :param framer: The modbus framer to use (default ModbusSocketFramer)
        :param timeout: The timeout to use for this socket (default None)
        """
        self.host = host
        self.port = port
        self.socket = None
        self.timeout = kwargs.get('timeout', None)
        BaseModbusClient.__init__(self, framer(ClientDecoder(), self), **kwargs)

    @classmethod
    def _get_address_family(cls, address):
        """ A helper method to get the correct address family
        for a given address.

        :param address: The address to get the af for
        :returns: AF_INET for ipv4 and AF_INET6 for ipv6
        """
        try:
            _ = socket.inet_pton(socket.AF_INET6, address)
        except socket.error: # not a valid ipv6 address
            return socket.AF_INET
        return socket.AF_INET6

    def connect(self):
        """ Connect to the modbus tcp server

        :returns: True if connection succeeded, False otherwise
        """
        if self.socket:
            return True
        try:
            family = ModbusUdpClient._get_address_family(self.host)
            self.socket = socket.socket(family, socket.SOCK_DGRAM)
            self.socket.settimeout(self.timeout)
        except socket.error as ex:
            _logger.error('Unable to create udp socket %s' % ex)
            self.close()
        return self.socket is not None

    def close(self):
        """ Closes the underlying socket connection
        """
        self.socket = None

    def _send(self, request):
        """ Sends data on the underlying socket

        :param request: The encoded request to send
        :return: The number of bytes written
        """
        if not self.socket:
            raise ConnectionException(self.__str__())
        if request:
            return self.socket.sendto(request, (self.host, self.port))
        return 0

    def _recv(self, size):
        """ Reads data from the underlying descriptor

        :param size: The number of bytes to read
        :return: The bytes read
        """
        if not self.socket:
            raise ConnectionException(self.__str__())
        return self.socket.recvfrom(size)[0]

    def is_socket_open(self):
        if self.socket:
            return True
        return self.connect()

    def __str__(self):
        """ Builds a string representation of the connection

        :returns: The string representation
        """
        return "ModbusUdpClient(%s:%s)" % (self.host, self.port)

    def __repr__(self):
        return (
            "<{} at {} socket={self.socket}, ipaddr={self.host}, "
            "port={self.port}, timeout={self.timeout}>"
        ).format(self.__class__.__name__, hex(id(self)), self=self)


# __all__ = [
#     "ModbusTcpClient", "ModbusTlsClient", "ModbusUdpClient", "ModbusSerialClient"
# ]

__all__ = [
    "ModbusUdpClient"
]
