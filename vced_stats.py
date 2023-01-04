#!/usr/bin/env python3
import csv
import json
import math
import os
import pathlib
import time
from contextlib import closing
from io import StringIO
from typing import List

import grpc
import mysql.connector

import partner_api2_pb2_grpc as api
from partner_api2_pb2 import *

# Load the config
config_path = os.path.normpath(os.path.join(pathlib.Path(__file__).parent.resolve(), 'config.json'))
with open(config_path, 'r') as config_file:
    config = json.load(config_file)

# Establish a connection to the server...
creds = grpc.ssl_channel_credentials()
channel = grpc.secure_channel(f"{config['api_root']}:{config['api_port']}", creds)
# client stub (blocking)
stub = api.PartnerApiStub(channel)

request = AuthenticationRequest()
request.partner_email = config['username']
request.password = config['password']
auth_response = stub.Authenticate(request=request)

auth_token = auth_response.auth_token

# get list of devices managed by partner
inventoryRequest = DeviceInventoryRequest()
inventoryRequest.auth_token = auth_token
inventoryResponse = stub.GetDevices(inventoryRequest)

# Get the list of active vue2 devices
devices = [dev for dev in inventoryResponse.devices if dev.model == DeviceInventoryResponse.Device.DeviceModel.Vue2]


def write_to_db(values: List[dict]):
    with closing(mysql.connector.connect(**config['db'])) as conn:
        with closing(conn.cursor()) as cur:
            for data in values:
                cur.execute(
                    'INSERT IGNORE INTO usage_data (device_id, channel_id, channel_type, channel_direction, channel_usage, timestamp) VALUES (%s, %s, %s, %s, %s, %s);',
                    [data['device_id'], data['channel_id'], data['channel_type'], data['channel_direction'], data['channel_usage'],
                     data['timestamp']])
        conn.commit()


def store_detailed_usage() -> List[dict]:
    """ Gets usage info for all circuits on all devices. Returns usage for all circuits as a
    list of a list of dictionaries, with the circuit info combined with usage.
    (Why didn't they design the API so that you don't have to combine the circuit types
    manually?) """

    now = math.ceil(time.time())
    usage_request = DeviceUsageRequest()
    usage_request.auth_token = auth_token
    usage_request.start_epoch_seconds = now - 86400  # one day's worth of 15 minute intervals
    usage_request.end_epoch_seconds = now
    usage_request.scale = DataResolution.FifteenMinutes
    usage_request.channels = DeviceUsageRequest.UsageChannel.ALL
    usage_request.manufacturer_device_ids.extend([_.manufacturer_device_id for _ in devices])

    usage_response = stub.GetUsageData(usage_request)

    def get_circuit_info(manufacturer_id, channel_id):
        for vue2 in devices:
            if vue2.manufacturer_device_id == manufacturer_id:
                for channel in vue2.circuit_infos:
                    if channel.channel_number == channel_id:
                        info = {'device_id': manufacturer_id, 'channel_id': channel_id, 'channel_direction': channel.energy_direction}
                        if channel.channel_number < 4:
                            info['channel_type'] = 'Mains'
                        else:
                            info['channel_type'] = channel.sub_type
                        if info['channel_type'] == '':
                            info['channel_type'] = 'Unspecified/Unknown'
                        return info
        raise ValueError('Failed to find device or channel - this is probably a mismatch in the API response.')

    to_insert = []
    for usage_data in usage_response.device_usages:
        timestamps = {}
        # Go through the timestamps
        for position, timestamp in enumerate(usage_data.bucket_epoch_seconds):
            timestamps[position] = timestamp
        for channel_usage in usage_data.channel_usages:
            circuit_data = get_circuit_info(usage_data.manufacturer_device_id, channel_usage.channel)
            for pos, usage_at_time in enumerate(channel_usage.usages):
                circuit_copy = circuit_data.copy()
                circuit_copy['channel_usage'] = usage_at_time
                circuit_copy['timestamp'] = timestamps[pos]
                to_insert.append(circuit_copy)

    return to_insert


if __name__ == "__main__":
    detailed_usage = store_detailed_usage()

    # Write results to the DB, if possible, otherwise print as CSV
    if 'db' not in config or 'user' not in config['db'] or config['db']['user'] == 'changeme':
        # Render results as CSV
        csv_file = StringIO()
        csv_writer = csv.DictWriter(csv_file,
                                    fieldnames=['device_id', 'channel_id', 'channel_direction', 'channel_type', 'channel_usage', 'timestamp'])
        csv_writer.writerows(detailed_usage)
        csv_file.seek(0)
        print(csv_file.read())
    else:
        write_to_db(detailed_usage)
