#!/usr/bin/env python3
import csv
import json
import math
import os
import pathlib
import time
from io import StringIO
from typing import List

import grpc

import mysql_functions
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

# Get the list of active vue2 (1) and vue3 (7) devices. (See partner_api2.proto lines 105-122)
devices = [dev for dev in inventoryResponse.devices if dev.model in [1,7]]

def store_detailed_usage(since: int, until: int = None) -> List[dict]:
    """ Gets usage info for all circuits on all devices. Returns usage for all circuits as a
    list of a list of dictionaries, with the circuit info combined with usage.
    (Why didn't they design the API so that you don't have to combine the circuit types
    manually?)

    Gets usage since the most recent timestamp.
    """

    if until is None:
        until = math.ceil(time.time())

    usage_request = DeviceUsageRequest()
    usage_request.auth_token = auth_token
    usage_request.start_epoch_seconds = since
    usage_request.end_epoch_seconds = until
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
    get_data_since, get_data_until = mysql_functions.get_most_recent_timestamp()
    detailed_usage = store_detailed_usage(get_data_since, get_data_until)

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
        mysql_functions.write_to_db(detailed_usage)
