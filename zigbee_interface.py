from pprint import pprint
from time import sleep
import re


ME = '1'
DATA_PATTERN = re.compile('([0-9A-Fa-f]{1,3})\|([CR])\|([0-9,;]+)\|(.*)')


class ZigbeeService(object):

    def __init__(self, port, data_handler):
        super(ZigbeeService, self).__init__()
        self.port = port
        self.data_handler = data_handler
        self.running = True

    @staticmethod
    def parse_raw_data(data):
        parsed = DATA_PATTERN.match(data)
        if not parsed:
            return
        msg_id, dtype, path, message = parsed.groups()

        prev_path, next_path = path.split(';')
        prev_path = [str(n) for n in prev_path.split(',')]
        next_path = [str(n) for n in next_path.split(',')]

        return {'msg_id': msg_id,
                'prev_path': prev_path,
                'next_path': next_path,
                'dtype': dtype,
                'message': message}

    @staticmethod
    def generate_raw_data(msg_id, prev_path, next_path, dtype, message):
        prev_path = ','.join(prev_path)
        next_path = ','.join(next_path)
        return '{};{}|{}|{}\n'.format(prev_path, next_path, dtype, message)

    def send(self, data):
        sleep(0.5)
        if not isinstance(data, bytes):
            data = data.encode()
        return self.port.write(data)

    def recv(self):
        return self.port.readline().decode().strip('\n')

    def process_data(self, data):
        response = {'msg_id': data['msg_id'],
                    # len(data['next_path']) == 1. so no need to reverse.
                    'prev_path': data['next_path'],
                    'next_path': list(reversed(data['prev_path'])),
                    'dtype': 'R',
                    'message': ''}
        response['message'] = self.data_handler(data['message'])
        return response

    def bounce_data(self, data):
        data['prev_path'].append(data['next_path'].pop(0))
        return data

    def sink_data(self):
        return

    def run(self):
        while self.running:
            print('\nLISTENING', end='')
            raw_data = self.recv()
            print('\rGOT DATA: "{}"'.format(raw_data))
            try:
                data = self.parse_raw_data(raw_data)
                pprint(data)
            except:
                print('INVALID DATA: "{}"'.format(raw_data))
                print('SINKED')
                continue
            # Got a response data
            if data['dtype'] == 'R':
                # Got a response and no more hops
                if len(data['next_path']) == 1:
                    # Oh it's for me
                    if data['next_path'][0] in ME:
                        print('RESPONSE FROM COMMAND: "{}"'.format(raw_data))
                        pprint(data)
                        continue
                    # It's not for me.
                    else:
                        print('SINKING')
                        self.sink_data()
                # Got a response and have some hops more.
                elif data['next_path'][0] in ME:
                    print('BOUNCING REPLY: "{}"'.format(raw_data))
                    response = self.bounce_data(data)
                    raw_response = self.generate_raw_data(**response)
                    self.send(raw_response)
            # Got a command and no more hops.
            elif len(data['next_path']) == 1:
                # It's for me. Doing my job
                if data['next_path'][0] in ME:
                    response = self.process_data(data)
                    raw_response = self.generate_raw_data(**response)
                    print('PROCESSING COMMAND: "{}"'.format(raw_data))
                    print('SENDING REPLY: "{}"'.format(
                        raw_response.strip('\n')))
                    self.send(raw_response)
                # Not for me. I don't care.
                else:
                    self.sink_data()

            # Got a command, I'm on the path.
            elif data['next_path'][0] in ME:
                response = self.bounce_data(data)
                raw_response = self.generate_raw_data(**response)
                print('BOUNCING: "{}"'.format(raw_response.strip('\n')))
                self.send(raw_response)

            # Got a command, I'm not on the path.
            else:
                print('IRRELEVANT FOR NOW: "{}"'.format(raw_data))
                print('SINKED')
                self.sink_data()

    def halt(self):
        self.running = False
        return self.port.close()
