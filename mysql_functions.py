import json
import os
import pathlib
import time
from contextlib import closing
from typing import List

import mysql.connector

config_path = os.path.normpath(os.path.join(pathlib.Path(__file__).parent.resolve(), 'config.json'))
with open(config_path, 'r') as config_file:
    config = json.load(config_file)


def write_to_db(values: List[dict]) -> None:
    with closing(mysql.connector.connect(**config['db'])) as conn:
        with closing(conn.cursor()) as cur:
            for data in values:
                try:
                    cur.execute(
                        'INSERT IGNORE INTO usage_data (device_id, channel_id, channel_type, channel_direction, channel_usage, timestamp) VALUES (%s, %s, %s, %s, %s, %s);',
                        [data['device_id'], data['channel_id'], data['channel_type'], data['channel_direction'], data['channel_usage'],
                         data['timestamp']])
                except:
                    print('Unable to write to db ',
                          data)
        conn.commit()


def get_most_recent_timestamp() -> (int, int):
    # Default to getting the last hour if we don't have a DB
    if 'db' not in config or 'user' not in config['db'] or config['db']['user'] == 'changeme':
        return int(time.time()) - 3600,int(time.time())

    with closing(mysql.connector.connect(**config['db'])) as conn:
        with closing(conn.cursor()) as cur:
            cur.execute('SELECT max(timestamp) AS most_recent FROM usage_data;', [])
            try:
                # Overlap by 31 minutes to make sure no data is missed
                since = cur.fetchone()[0] - 1860
                one_week_ago = int(time.time()) - 86400
                if since < one_week_ago:
                    print("Warning! No data records detected for more than a day. Fetching the next needed day "
                          "rather than the most recent day.")
                    return since, since + 86400
                else:
                    return since, int(time.time())
            except:
                print('Detected first run, getting data for last week. If seen more than once, this code is buggy.')
                return int(time.time()) - 604800, int(time.time())
