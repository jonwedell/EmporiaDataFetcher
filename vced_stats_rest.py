#!/usr/bin/env python3
import base64
import csv
import datetime
import json
import logging
import os
import pathlib
import sys
from io import StringIO

import requests

import mysql_functions

logger = logging.getLogger("EmporiaSampleClient")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter('%(asctime)s: %(levelname)s: %(message)s', datefmt='%H:%M:%S')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Load the config
config_path = os.path.normpath(os.path.join(pathlib.Path(__file__).parent.resolve(), 'config.json'))
with open(config_path, 'r') as config_file:
    config = json.load(config_file)


# Timestamp handling code
def timestamp_to_iso8601(unix_timestamp):
    dt = datetime.datetime.fromtimestamp(unix_timestamp)
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')
def iso8601_to_timestamp(iso8601_string):
    dt = datetime.datetime.strptime(iso8601_string, '%Y-%m-%dT%H:%M:%SZ')
    return int(dt.timestamp())

# To log in
def authenticate_with_client_credentials():
    cognito_domain, client_id, client_secret = config['cognito_domain'], config['client_id'], config['client_secret']

    token_url = f"{cognito_domain}/oauth2/token"
    auth_header = base64.urlsafe_b64encode(f"{client_id}:{client_secret}".encode()).decode()
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Authorization': f'Basic {auth_header}'
    }
    data = {'grant_type': 'client_credentials'}
    try:
        response = requests.post(token_url, headers=headers, data=data)
        response.raise_for_status()
        access_token = response.json().get('access_token')
        if not access_token:
            logger.error('Failed to get access_token from Cognito response')
            sys.exit(1)
        return access_token
    except requests.RequestException as e:
        logger.error('Failed to authenticate with Cognito: %s', e)
        sys.exit(1)

def get_usage_during_period(start_timestamp, end_timestamp) -> list[dict]:
    """ Returns a list of dictionaries as such:
     {'device_id': 'A2034A04B410521CB8CD50',
     'channel_id': 1,
     'channel_direction': 3,
     'channel_type': 'Mains',
     'channel_usage': 91.8388775422838,
     'timestamp': 1743436800}
     """

    # Authenticate and get the list of device IDs
    auth_token = authenticate_with_client_credentials()
    devices = requests.get(config['rest_api_root'] + "/v1/partner/devices", headers={'Authorization': auth_token}).json()
    monitor_ids = [_['device_id'] for _ in devices['devices'] if _['category'] == "MONITOR"]

    monitor_info = {}

    def batch(iterable, size):
        len_iter = len(iterable)
        for ndx in range(0, len_iter, size):
            yield iterable[ndx:min(ndx + size, len_iter)]

    # We have to operate on at most 100 at a time due to API restrictions
    for chunk in batch(monitor_ids, 100):
        # Get the information for each of the monitors
        r = requests.get(config['rest_api_root'] + "/v1/devices/energy-monitors",
                         headers={'Authorization': auth_token}, params={'device_ids': chunk})
        r.raise_for_status()
        for device in r.json()['success']:
            monitor_info[device['device_id']] = device
            monitor_info[device['device_id']]['circuit_map'] = {_['circuit_id']:_ for _ in device['circuits']}

        # Get the energy usage
        r = requests.get(config['rest_api_root'] + "/v1/devices/energy-monitors/circuits/usages/energy",
                              headers={'Authorization': auth_token},
                              params={'start': timestamp_to_iso8601(start_timestamp),
                                    'end':timestamp_to_iso8601(end_timestamp),
                                    'energy_resolution': "FIFTEEN_MINUTES",
                                    'device_ids': chunk,
                                    'circuit_ids': ['Main_1', 'Main_2', 'Main_3'] + list(range(1,16))})
        r.raise_for_status()
        for device in r.json()['success']:
            monitor_info[device['device_id']]['circuit_usages'] = device['circuit_usages']

    results = []
    direction_map = {'UNKNOWN_DIRECTION': 0,
                     'CONSUMPTION': 1,
                     'GENERATION': 2,
                     'BIDIRECTIONAL': 3}
    channel_map = {'Main_1': 1, 'Main_2': 2, 'Main_3': 3}
    for device_id, device in monitor_info.items():
        for circuit in device['circuit_usages']:
            circuit_data = device['circuit_map'][circuit['circuit_id']]
            for usage in circuit['usage']:
                if not usage['partial']:
                    # The +3 normalizes for the mains which used to be 1,2,3
                    circuit_id = channel_map[circuit_data['circuit_id']] if circuit_data['circuit_id'] in channel_map else int(circuit_data['circuit_id']) + 3
                    # Figure out the circuit type
                    circuit_type = 'Mains' if circuit_data['circuit_type'] == 'MAIN' else circuit_data['circuit_sub_type']
                    if not circuit_type:
                        circuit_type = 'Unspecified/Unknown'

                    results.append({'device_id': device_id,
                                    'channel_id': circuit_id,
                                    'channel_type': circuit_type,
                                    'channel_direction': direction_map[circuit_data['energy_direction']],
                                    'channel_usage': usage['energy_kwhs'] * 1000 * circuit_data['multiplier'],
                                    'timestamp': iso8601_to_timestamp(usage['interval']['end'])})

    return results


if __name__ == "__main__":
    get_data_since, get_data_until = mysql_functions.get_most_recent_timestamp()
    detailed_usage = get_usage_during_period(get_data_since, get_data_until)

    # Write results to the DB, if possible, otherwise print as CSV
    if 'db' not in config or 'user' not in config['db'] or config['db']['user'] == 'changeme':
        # Render results as CSV
        csv_file = StringIO()
        csv_writer = csv.DictWriter(csv_file,
                                    extrasaction='ignore',
                                    fieldnames=['device_id', 'channel_id', 'channel_direction', 'channel_type', 'channel_usage', 'timestamp'])
        csv_writer.writerows(detailed_usage)
        csv_file.seek(0)
        print(csv_file.read())
    else:
        mysql_functions.write_to_db(detailed_usage)
