###############################################################################
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#
###############################################################################

import csv
import json
import os
import sys

station2geom = {}


def station_to_geom(station_id=''):
    if station2geom == {}:
        with open('data/metadata/station/stations.geojson') as file:
            fc = json.loads(file.read())
            for f in fc['features']:
                wsid = f['properties']['wigos_id']
                geom = zip(('X', 'Y', 'Z'), f['geometry']['coordinates'])
                station2geom[wsid] = {key: val for (key, val) in geom}
    if station_id:
        return station2geom[station_id]


def walk_path(path):
    """
    Walks os directory path collecting all CSV files.

    :param path: required, string. os directory.
    :return: list. List of csv paths.
    """
    file_list = []
    for root, _, files in os.walk(path, topdown=False):
        for name in files:
            if name == 'observations.csv':
                continue
            file_list.append(os.path.join(root, name))

    return file_list


def _handle_csvs(files, csv_out=[]):
    """
    Splits list of csv files into individual csv files.

    :param files: required, string. URL to be shortened.
    """
    for f in files:
        print(f'Reading file: {os.path.basename(f)}\r', end='')
        csv_out = parse_csv(f, csv_out)

    print('\r\r')
    return csv_out


def handle_csv(file):
    """
    Parses and shortens CSV file.

    :param file: required, string or list of strings.
    """
    if isinstance(file, list) and len(file) > 0:
        return _handle_csvs(file)
    else:
        return parse_csv(file)


def parse_csv(filename, ret_csv=[]):
    """
    Parse CSV file into csv.

    :param filename: required, string. URL to be shortened.
    :return: list. Parsed csv.
    """

    with open(filename, mode='r') as fp:

        csv_reader = csv.reader(fp)
        headers = [h.strip() for h in next(csv_reader)]
        headers.extend(['X', 'Y', 'Z'])
        if len(ret_csv) == 0:
            ret_csv.append(headers)
        for line in csv_reader:
            station_id = line[headers.index('Station_ID')].strip().upper()
            parsed_line = []
            for h in ret_csv[0]:
                if h == 'X' or h == 'Y' or h == 'Z':
                    parsed_line.append(station_to_geom(station_id)[h])
                elif h in headers:
                    parsed_line.append(line[headers.index(h)].strip())
                else:
                    parsed_line.append("")

            ret_csv.append(parsed_line)

    return ret_csv


def write_csv(filename, content):
    print(f'Writing to: {filename}')
    with open(filename, 'w', newline='') as csvfile:
        csv.writer(csvfile).writerows(content)
    print('done')


if __name__ == "__main__":
    station_to_geom()
    if len(sys.argv) == 1:
        print('Usage: {} <path/to/data.csv>'.format(sys.argv[0]))
        sys.exit(1)

    path = sys.argv[1]
    file = path if path.endswith('.csv') else walk_path(path)

    csv_out = handle_csv(file)

    write_csv('observations.csv', csv_out)
