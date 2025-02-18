import datetime
import asyncio
import aioconsole
import json
import os
import ssl
import time
import sys

os.system('Color')

# SSL cert path (Self-signed)
cert = "./certs/cert.pem"

# Hostname / Ip, and Port number of the server
host, port = ('localhost', 9090)

ssl_connection = False


# Color codes for terminal coloring
class Color:
    BLUE = '\033[94m'
    GREY = '\033[90m'
    RED = '\033[31m'
    YELLOW = '\033[33m'
    END = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class Client:
    def __init__(self):
        self.host = host
        self.port = port
        self.username = None
        self.writer = None
        self.reader = None
        self.connected = False
        self.logged_in = False

        self.message_count = 0

        # server info that will be sent on successful connection
        self.username_max = None
        self.message_max = None
        self.current_channel = 'Main'

    # Closes connection client side.
    async def leave(self):
        self.connected = False
        if not self.writer.is_closing():
            self.writer.close()
            await self.writer.wait_closed()
        await self.press_to_continue()

    @staticmethod
    async def press_to_continue():
        await aioconsole.ainput("Press Enter to continue...")

    # tries to connect to server until successful
    async def connect(self):
        if ssl_connection:
            ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            ssl_context.check_hostname = False
            ssl_context.load_verify_locations(cert)

        """Attempts to connect to the server / host until it is accepted. Using connect_ex to prevent exceptions"""
        while not self.connected:
            print(f'Connecting to (HOST: {self.host}) (PORT: {self.port})...')
            try:
                if ssl_connection:
                    self.reader, self.writer = await asyncio.open_connection(host, port, ssl=ssl_context)
                else:
                    self.reader, self.writer = await asyncio.open_connection(host, port)

                print(f"Connected to {self.writer.get_extra_info('peername')}\n")
                data = await self.receive_data()
                self.username_max = data['username_length']
                self.message_max = data['message_length']

                self.connected = True

            # Server offline or unreachable
            except ConnectionRefusedError:
                continue
        
    async def login(self):
        """Takes in the user's login and saves the username, the password is just input and is not stored anywhere"""
        #  is not used since this is in a testing phase, you can put whatever.
        #  Please do not use an actual password as it is plain-text
        while not self.logged_in:
            try:
                data = await self.receive_data()
                if data is None:
                    raise ConnectionError("Invalid data received from the server.")

                message_type = data.get('message_type')
                message = data.get('message')

                if message_type == 'REQUEST' and message == 'LOGIN':
                    self.username = input('Username: ')
                    password = input('Password: ')
                    data = json.dumps({'username': self.username, 'password': password}).encode() + b'\n'
                    self.writer.write(data)
                    await self.writer.drain()

                    print("Awaiting Confirmation...")
                elif message_type == 'PERMIT' and message == 'LOGIN':
                    self.logged_in = True
                    return
                elif message_type == 'DENY':
                    if message == 'BANNED':
                        print("You are banned!")
                        if self.connected:
                            await self.leave()
                            return
                    elif message == 'LENGTH':
                        print(f"Username too long! Usernames must be less than {self.username_max} characters")
                        continue
                    elif message == 'TAKEN':
                        print(f"Username {self.username}, is already taken. Please select another name")
                else:
                    raise ConnectionError("Invalid response from the server.")
            except ConnectionError as e:
                if self.connected:
                    await self.leave()
                    print(f"Login failed: {e}")
                    return

    async def send_message(self, message, message_type='INFO'):
        data = (json.dumps({'message': message, 'message_type': message_type, 'time': str(time.time())})+'\n').encode()
        self.writer.write(data)
        await self.writer.drain()

    # Formats message according to the client. Client side only. Customizable
    async def format_message(self, message_data):

        sender = message_data['sender']
        message = message_data['message']
        unix_time = message_data['time']
        date_time = datetime.datetime.fromtimestamp(int(float(unix_time))).strftime("%m/%d/%Y %#I:%M %p")

        # Blue for your username, Red for other, yellow for Server
        if sender == self.username:
            return f"{Color.BLUE}{self.username}{Color.GREY} : {Color.END}{message} {Color.GREY}{date_time}{Color.END}"
        elif sender == 'Server':
            return f"{Color.YELLOW}{sender}{Color.GREY} : {Color.END}{message} {Color.GREY}{date_time}{Color.END}"
        else:
            return f"{Color.RED}{sender}{Color.GREY} : {Color.END}{message} {Color.GREY}{date_time}{Color.END}"

    async def receive_data(self):
        try:
            data = await self.reader.readuntil(b'\n')
            data = data.decode()
            data = json.loads(data)
            return data
        except (asyncio.IncompleteReadError, ConnectionResetError):
            # Handles the exception when the connection is closed by the server
            print("Connection closed by the server")
            if self.connected:
                await self.leave()
            return
        
    async def filter_data(self, data):
        message_type = data['message_type']
        message = data['message']

        if message_type == 'SYN':
            time_1 = data['time']
            time_2 = time.time()
            await self.send_message(str(time_2), message_type='ACK')
            latency = round(float(time_2) - float(time_1))
            os.system(f"title Latency (s): {latency}    Channel : {self.current_channel}")

        elif message_type == 'CHANNEL_CHANGE':
            if message is None:
                self.current_channel = 'Main'
            else:
                self.current_channel = message 
        else:
            return data

    async def client_handler(self):
        """Receives messages from the server and checks the message data for usernames.
         Basic coloring for other names and the server messages"""
        while self.logged_in:
            data = await self.receive_data()
            if data is None:
                if self.connected:
                    await self.leave()
                return

            data = await self.filter_data(data)
            if data is None:
                continue

            message = await self.format_message(data)
            if data['sender'] == self.username:
                print(message)
            else:
                print(message)

    async def receive_input(self):
        """Sends the message to the server / host machine."""
        while self.logged_in:
            message = await aioconsole.ainput()
            sys.stdout.write('\x1b[1A')
            sys.stdout.write('\x1b[2K')

            # change this cap if you would like, serverside will send this info on first connection eventually
            if len(message) > self.message_max:
                # Server checks this value, but it saves resources checking on client to prevent it in the first place.
                print('Message Too Long!')
            else:
                try:
                    await self.send_message(message)
                except ConnectionResetError:
                    if self.connected:
                        await self.leave()
                    return
    
    async def run_client(self):
        await self.connect()
        await self.login()
        receive_message = asyncio.create_task(client.client_handler())
        send_message = asyncio.create_task(client.receive_input())
        await asyncio.gather(receive_message, send_message)


client = Client()
asyncio.run(client.run_client())

