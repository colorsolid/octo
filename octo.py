import json
import os
import requests
import threading
import time
import websocket


BASE_DIR = os.path.realpath(os.path.dirname(__file__))

if os.path.isfile('octo.log'):
    os.remove('/home/pi/octo.log')


env_vars = {}
with open(os.path.join(BASE_DIR, 'vars.txt'), 'r') as infile:
    var_lines = list(infile.readlines())
    for var in var_lines:
        try:
            k, v = var.strip().split('=')
            if k[0] != '#':
                env_vars[k] = v
        except ValueError:
            pass  # no variable found


def _print(text):
    print('logging', text)
    with open('/home/pi/octo.log', 'a+') as logfile:
        logfile.write(text + '\n')


class WebSocketThread(threading.Thread):
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.opened = False
        self.reopen = True
        self.daemon = True
        self.key = env_vars['WS_KEY']
        self.start()

    def run(self):
        self.connect()

    def connect(self):
        self.connection = websocket.WebSocketApp(
            self.url,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        self.connection.on_open = self.on_open
        _print(f'connecting {self.url}')
        self.connection.run_forever()

    def on_message(self, *args):
        _print(f'message {args}')
        # data = json.loads(message)
        # print('msg', data)

    def on_error(self, *args):
        _print(f'error {args}')

    def on_close(self, *args):
        _print(f'closed {args}')
        self.opened = False
        if self.reopen:
            time.sleep(5)
            self.connect()

    def on_open(self, *args):
        self.opened = True
        _print('open')


class APIInterface:
    def __init__(self):
        self.job_url = f'http://{env_vars["OCTO_URL"]}/api/job'
        self.tool_url = f'http://{env_vars["OCTO_URL"]}/api/printer?exclude=sd,state'
        self.headers = {'X-Api-Key': env_vars['OCTO_KEY']}
        self.data = {}

    def get_data(self):
        job_r = requests.get(self.job_url, headers=self.headers).json()
        printer_status = job_r['state']
        file_name = job_r['job']['file']['name']
        elapsed_time = job_r['progress']['printTime']
        estimated_time = job_r['job']['estimatedPrintTime']
        file_size = job_r['job']['file']['size']
        file_pos = job_r['progress']['filepos']
        progress = int((job_r['progress']['completion'] or 0))

        tool_r = requests.get(self.tool_url, headers=self.headers).json()
        try:
            b_temp = tool_r['temperature']['bed']['actual']
            e_temp = tool_r['temperature']['tool0']['actual']
        except (json.decoder.JSONDecodeError, KeyError):
            _print('Octoprint not connected to printer')

        new_data = {
            'printer_status': printer_status,
            'file_name': file_name,
            'elapsed_time': elapsed_time,
            'estimated_time': estimated_time,
            'b_temp': b_temp,
            'e_temp': e_temp,
            'file_size': file_size,
            'file_pos': file_pos,
            'progress': progress
        }

        send_data = {}

        for k, v in new_data.items():
            if k in self.data:
                if self.data[k] != v:
                    send_data[k] = v
            else:
                send_data[k] = v

        self.data = new_data
        return send_data


if __name__ == '__main__':
    ws = WebSocketThread(env_vars['WS_URL'])
    interface = APIInterface()
    while True:
        try:
            data = interface.get_data()
            if hasattr(ws.connection, 'sock') and hasattr(ws.connection.sock, 'sock'):
                if ws.connection.sock.sock and data:
                    ws.connection.send(json.dumps({
                        'printer_socket_key': ws.key,
                        'data': data
                    }))
                else:
                    _print('no sock.sock')
        except Exception as e:
            _print(f'Octoprint not running {e}')
        time.sleep(5)
    # ws.reopen = False
    # ws.connection.close()
    # ws.join()
