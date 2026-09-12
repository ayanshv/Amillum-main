"""Authenticated local Unix socket bridge; no TCP listener or cloud transport.

JSON with explicit message/size limits is used instead of executable pickle data.
The random session credential is inherited by the native child, never sent to JS.
"""

import hmac
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import tempfile
import threading

MAX_MESSAGE = 131072


def read_message(connection):
    data = bytearray()
    while len(data) <= MAX_MESSAGE:
        block = connection.recv(min(4096, MAX_MESSAGE + 1 - len(data)))
        if not block:
            raise ValueError('Incomplete bridge message')
        data.extend(block)
        if b'\n' in block:
            if len(data) > MAX_MESSAGE or data.count(b'\n') != 1 or not data.endswith(b'\n'):
                raise ValueError('Invalid bridge message')
            result = json.loads(data)
            if not isinstance(result, dict):
                raise ValueError('Invalid bridge message')
            return result
    raise ValueError('Bridge message too large')


def send_message(connection, data):
    encoded = json.dumps(data, separators=(',', ':')).encode() + b'\n'
    if len(encoded) > MAX_MESSAGE:
        raise ValueError('Bridge message too large')
    connection.sendall(encoded)


class BridgeServer:
    def __init__(self, state):
        self.state = state
        self.directory = Path(tempfile.mkdtemp(prefix='amillum-', dir='/tmp'))
        self.path = str(self.directory / 'native.sock')
        self.token = secrets.token_hex(32)
        self.stopped = threading.Event()
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.bind(self.path)
        os.chmod(self.path, 0o600)
        self.socket.listen(4)
        self.socket.settimeout(.25)
        self.thread = threading.Thread(target=self.serve, name='amillum-local-bridge', daemon=True)

    def start(self):
        os.environ['AMILLUM_BRIDGE_PATH'] = self.path
        os.environ['AMILLUM_BRIDGE_TOKEN'] = self.token
        self.thread.start()

    def serve(self):
        while not self.stopped.is_set():
            try:
                connection, _ = self.socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with connection:
                connection.settimeout(.5)
                try:
                    message = read_message(connection)
                    token = message.get('token')
                    if not isinstance(token, str) or not hmac.compare_digest(token, self.token):
                        send_message(connection, {'error': 'unauthorized'})
                    elif message.get('op') == 'policy':
                        send_message(connection, self.state.heartbeat())
                    elif message.get('op') == 'panel_state':
                        send_message(connection, self.state.panel_state())
                    elif message.get('op') == 'cancel_context' and isinstance(message.get('payload'),dict):
                        send_message(connection, {'accepted':self.state.cancel_context(message['payload'])})
                    elif message.get('op') == 'publish' and isinstance(message.get('payload'), dict):
                        send_message(connection, {'accepted': self.state.publish(message['payload'])})
                    elif message.get('op') == 'begin_context' and isinstance(message.get('payload'), dict):
                        send_message(connection, self.state.begin_context(message['payload']))
                    elif message.get('op') == 'finish_context' and isinstance(message.get('payload'), dict):
                        send_message(connection, {'accepted': self.state.finish_context(message['payload'])})
                    elif message.get('op') == 'context_valid' and isinstance(message.get('payload'), dict):
                        send_message(connection, {'valid': self.state.context_valid(message['payload'])})
                    elif message.get('op') == 'permissions' and isinstance(message.get('payload'), dict):
                        self.state.report_permissions(message['payload'])
                        send_message(connection, {'accepted': True})
                    else:
                        send_message(connection, {'error': 'unsupported operation'})
                except (OSError, ValueError, TypeError, RecursionError):
                    pass  # Malformed requests cannot mutate policy or terminate the bridge.

    def close(self):
        self.stopped.set()
        self.socket.close()
        if self.thread.is_alive():
            self.thread.join(timeout=1)
        shutil.rmtree(self.directory, ignore_errors=True)
        if os.environ.get('AMILLUM_BRIDGE_PATH') == self.path:
            os.environ.pop('AMILLUM_BRIDGE_PATH', None)
            os.environ.pop('AMILLUM_BRIDGE_TOKEN', None)


def request(op, payload=None, *, path=None, token=None):
    path = path or os.environ.get('AMILLUM_BRIDGE_PATH')
    token = token or os.environ.get('AMILLUM_BRIDGE_TOKEN')
    if not path or not token:
        raise ConnectionError('Native bridge unavailable')
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(.75)
        connection.connect(path)
        send_message(connection, {'op': op, 'payload': payload, 'token': token})
        response = read_message(connection)
        if 'error' in response:
            raise ConnectionError('Native bridge rejected request')
        return response


_server = None


def configure_server(app):
    global _server
    if _server is not None:
        return
    from core.context_awareness import get_state
    _server = BridgeServer(get_state())
    _server.start()
    app.on_shutdown(_server.close)
