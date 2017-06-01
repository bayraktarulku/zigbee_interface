from pprint import pprint
from time import sleep, time
from models import Data, DBSession
from config import ME, TIMEOUT_THRESHOLD
from sqlalchemy import and_
import re


DATA_PATTERN = re.compile('([0-9A-Fa-f]{1,3})\|([CR])\|([0-9,;]+)\|(.*)')


class ZigbeeService(object):

    def __init__(self, port, data_handler):
        super(ZigbeeService, self).__init__()
        self.port = port
        self.data_handler = data_handler
        self.running = True

    def _cleanup(self):
        now = time()
        session = DBSession()
        session.query(Data).filter(now - Data.timestamp > TIMEOUT_THRESHOLD).delete()
        session.commit()
        session.close()

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
        return '{};{}|{}|{}'.format(prev_path, next_path, dtype, message)

    def send(self, data):
        sleep(0.5)
        if not isinstance(data, bytes):
            data = (data + '\n').encode()
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

    def is_unique(self, data):
        session = DBSession()
        ref_check = session.query(Data).filter(
            and_(Data.msg_id == data['msg_id'],
                 Data.dtype == data['dtype'])).count()
        return ref_check == 0

    def save_data(self, data):
        session = DBSession()
        temp = data.copy()
        temp['timestamp'] = time()
        new_record = Data(**temp)
        session.add(new_record)
        session.commit()
        session.close()

    def validate(self, data):
        self._cleanup()
        if self.is_unique(data):
            self.save_data(data)
            return True
        return False

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
            if not self.validate(data):
                print('DUPLICATED PACKAGE, SINKING: "{}"'.format(raw_data))
                continue

            # Data is irrelevant
            if ME not in data['next_path']:
                print('IRRELEVANT DATA: "{}"'.format(raw_data))
                print('SINKED.')
                continue

            # Data should pass from me or data is for me.
            fasten_flag = False
            while ME != data['next_path'][0]:
                fasten_flag = True
                data = self.bounce_data(data)
            if fasten_flag:
                print('FASTER PROCESS!')

            # Data is for me
            if len(data['next_path']) == 1:
                response = self.process_data(data)

            # Data is not for me, but it should pass from me
            else:
                response = self.bounce_data(data)
            self.send(response)

    def halt(self):
        self.running = False
        return self.port.close()
