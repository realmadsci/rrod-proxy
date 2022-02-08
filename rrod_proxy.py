# Required packages:
# `python -m pip install trio colorama termcolor`
import msvcrt

from colorama import init
from termcolor import cprint
import trio

# Set up terminal coloring for Windows
init()


async def handle_keypress(key, client, server):
    """
    Handle keypresses

    NOTE: This is only called when the proxy is up and connected, so the client and server sockets should
          always be valid capable of sending data inside this function.

    NOTE: The Esc key b"\x1b" and Ctrl-C b"\x03" are already taken to mean "exit" so you'll never see them in here!
    """
    cprint(f"Got key: '{key}'", "yellow")


async def handle_client_to_server_data(data, client, server):
    """
    Handle data that has arrived from the client and is heading to the server.

    You can either do the simple "send it along" thing like so:
    `await server.send(data)`
    or you can do fancier things, even including spoofing data back to the client if you wish.
    """
    cprint("Client ---> Server\n" + data.hex(" "), "green")
    await server.send(data)


async def handle_server_to_client_data(data, client, server):
    """
    Handle data that has arrived from the server and is heading to the client.

    You can either do the simple "send it along" thing like so:
    `await client.send(data)`
    or you can do fancier things, even including spoofing data back to the server if you wish.
    """
    cprint("Client <--- Server\n" + data.hex(" "), "blue")
    await client.send(data)


class TcpProxy:
    def __init__(self, client_port, server_ip, server_port):
        self.client_port = client_port
        self.server_ip = server_ip
        self.server_port = server_port
        self.client_conn = None
        self.server_conn = None

    async def run(self):
        # Create a TCP socket to listen locally
        with trio.socket.socket(
            family=trio.socket.AF_INET,  # IPv4
            type=trio.socket.SOCK_STREAM,  # TCP
        ) as client_sock:
            # NOTE: This binds to ONLY the localhost interface, so nothing outside of this local host can connect to it!
            await client_sock.bind(("127.0.0.1", self.client_port))
            client_sock.listen()

            # This loop will reconnect things whenever the client socket drops, so we don't have to keep restarting this proxy for every connection:
            while True:
                (self.client_conn, addr) = await client_sock.accept()
                # NOTE: We *could* spawn off multiple child tasks here and open multiple parallel connections with accept() but we _don't_ for
                # simplicity and because the goal of this proxy is to study/manipulate the connection (rather than actually be a proxy):
                with self.client_conn:
                    print(
                        f"Connected by {addr}, connecting to {self.server_ip}:{self.server_port}"
                    )
                    with trio.socket.socket(
                        family=trio.socket.AF_INET,  # IPv4
                        type=trio.socket.SOCK_STREAM,  # TCP
                    ) as self.server_conn:
                        await self.server_conn.connect(
                            (self.server_ip, self.server_port)
                        )

                        async def server_recv_loop(cancel_scope):
                            # Loop forever, sending received traffic to the client
                            try:
                                while True:
                                    data = await self.server_conn.recv(4096)
                                    if not data:
                                        cprint(f"Server disconnected.", "red")
                                        break

                                    await handle_server_to_client_data(
                                        data, self.client_conn, self.server_conn
                                    )

                            except Exception as e:
                                cprint(f"Client <--- Server exception: {e}", "red")

                            # Close down all tasks
                            cancel_scope.cancel()

                        async def client_recv_loop(cancel_scope):
                            # Loop forever, sending received traffic to the server
                            try:
                                while True:
                                    data = await self.client_conn.recv(4096)
                                    if not data:
                                        cprint(f"Client disconnected.", "red")
                                        break

                                    await handle_client_to_server_data(
                                        data, self.client_conn, self.server_conn
                                    )

                            except Exception as e:
                                cprint(f"Client ---> Server exception: {e}", "red")

                            # Close down all tasks
                            cancel_scope.cancel()

                        async with trio.open_nursery() as nursery:
                            nursery.start_soon(server_recv_loop, nursery.cancel_scope)
                            nursery.start_soon(client_recv_loop, nursery.cancel_scope)


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
            ch = b"\xE0" + ch2
        yield ch


async def main():
    # tcp_proxy = TcpProxy(prt, "ip", prt)

    async with trio.open_nursery() as root_nursery:

        # Run the TCP proxy:
        root_nursery.start_soon(tcp_proxy.run)

        # Handle keypresses
        async for key in getch_iterator():
            if key == b"\x1b" or key == b"\x03":
                cprint(f"Received escape key. Exiting...", "red")
                root_nursery.cancel_scope.cancel()

            # Snooping into `_sock._closed` private variable is sketch, but :shrug:
            elif (
                tcp_proxy.client_conn is not None
                and not tcp_proxy.client_conn._sock._closed
                and tcp_proxy.server_conn is not None
                and not tcp_proxy.server_conn._sock._closed
            ):
                await handle_keypress(key, tcp_proxy.client_conn, tcp_proxy.server_conn)


trio.run(main)
