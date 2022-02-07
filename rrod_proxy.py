# Required packages:
# `python -m pip install trio colorama termcolor`


# If you want to use IPv6, then:
# - replace AF_INET with AF_INET6 everywhere
# - use the hostname "2.pool.ntp.org"
#   (see: https://news.ntppool.org/2011/06/continuing-ipv6-deployment/)

import datetime
import msvcrt
import struct

from colorama import init
from termcolor import cprint
import trio

# Set up terminal coloring for Windows
init()

class TcpProxy:
    def __init__(self, client_port, server_ip, server_port):
        self.client_port = client_port
        self.server_ip = server_ip
        self.server_port = server_port

    async def run(self):
        # Create a TCP socket to listen locally
        with trio.socket.socket(
            family=trio.socket.AF_INET,     # IPv4
            type=trio.socket.SOCK_STREAM,   # TCP
        ) as client_sock:
            # NOTE: This binds to ONLY the localhost interface, so nothing outside of this local host can connect to it!
            await client_sock.bind(("127.0.0.1", self.client_port))
            client_sock.listen()

            # This loop will reconnect things whenever the client socket drops, so we don't have to keep restarting this proxy for every connection:
            while True:
                (conn, addr) = await client_sock.accept()
                # NOTE: We *could* spawn off multiple child tasks here and open multiple parallel connections with accept() but we _don't_ for
                # simplicity and because the goal of this proxy is to study/manipulate the connection (rather than actually be a proxy):
                with conn:
                    print(f"Connected by {addr}, connecting to {self.server_ip}:{self.server_port}")
                    with trio.socket.socket(
                        family=trio.socket.AF_INET,     # IPv4
                        type=trio.socket.SOCK_STREAM,   # TCP
                    ) as server_sock:
                        await server_sock.connect((self.server_ip, self.server_port))

                        async def server_recv_loop():
                            # Loop forever, sending received traffic to the client
                            while True:
                                data = await server_sock.recv(4096)
                                if not data:
                                    break
                                cprint("Client <--- Server\n" + data.hex(' '), 'red')
                                await conn.send(data)

                        async def client_recv_loop():
                            # Loop forever, sending received traffic to the server
                            while True:
                                data = await conn.recv(4096)
                                if not data:
                                    break
                                cprint("Client ---> Server\n" + data.hex(' '), 'green')
                                await server_sock.send(data)

                        async with trio.open_nursery() as nursery:
                            nursery.start_soon(server_recv_loop)
                            nursery.start_soon(client_recv_loop)


# THIS IS WINDOWS-ONLY!
# For a Linux-based version, things get a little easier and you can just use "select" type things to read from stdin,
# or something like this: https://stackoverflow.com/a/56640807
async def getch_iterator():
    """Return an interator of keypresses from getch"""
    while True:
        ch = await trio.to_thread.run_sync(msvcrt.getch, cancellable=True)
        # Handle special chars by sending a byte string prefixed with 0xE0
        if ch[0] == 0 or ch[0] == 0xE0:
            ch2 = await trio.to_thread.run_sync(msvcrt.getch, cancellable=True)
            # Prefix 0xE0 to the front.
            ch = b'\xE0' + ch2
        yield ch

async def main():
    #tcp_proxy = TcpProxy(prt, "remote_ip", prt)

    # Read responses from the socket.
    with trio.move_on_after(1000):
        async with trio.open_nursery() as nursery:

            nursery.start_soon(tcp_proxy.run)

            async for key in getch_iterator():
                print(f"Got key: '{key}'")
                if key == b'q':
                    nursery.cancel_scope.cancel()

trio.run(main)