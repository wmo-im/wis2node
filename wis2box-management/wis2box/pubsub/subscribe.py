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

import json
import logging
import multiprocessing as mp

from time import sleep

import click

from wis2box.api import upsert_collection_item
from wis2box import cli_helpers
import wis2box.data as data_
from wis2box.api import remove_collection, setup_collection
from wis2box.data_mappings import get_data_mappings
from wis2box.env import (BROKER_HOST, BROKER_PORT, BROKER_USERNAME,
                         BROKER_PASSWORD, STORAGE_SOURCE, STORAGE_ARCHIVE)
from wis2box.handler import Handler, NotHandledError
import wis2box.metadata.discovery as discovery_metadata
from wis2box.plugin import load_plugin, PLUGINS
from wis2box.pubsub.message import gcm

LOGGER = logging.getLogger(__name__)


class WIS2BoxSubscriber:

    def __init__(self, broker):
        self.data_mappings = get_data_mappings()
        self.broker = broker
        self.broker.bind('on_message', self.on_message_handler)
        self.broker.sub('wis2box/#')

    def handle(self, filepath, message):
        try:
            LOGGER.info(f'Processing {message} for {filepath}')
            # load handler
            handler = Handler(filepath=filepath,
                              data_mappings=self.data_mappings)
            if handler.handle():
                LOGGER.info('Data processed')
                for plugin in handler.plugins:
                    for filepath in plugin.files():
                        LOGGER.info(f'Public filepath: {filepath}')
        except NotHandledError as err:
            msg = f'not handled error: {err}'
            LOGGER.debug(msg)
        except ValueError as err:
            msg = f'handle() error: {err}'
            LOGGER.error(msg)
        except Exception as err:
            msg = f'handle() error: {err}'
            raise err

    def on_message_handler(self, client, userdata, msg):
        LOGGER.debug(f'Raw message: {msg.payload}')

        topic = msg.topic
        message = json.loads(msg.payload)
        LOGGER.info(f'Incoming message on topic {topic}')
        filepath = None
        if topic == 'wis2box/notifications':
            LOGGER.info(f'Notification: {message}')
            # store notification in messages collection
            upsert_collection_item('messages', message)
        elif (topic == 'wis2box/storage' and
              message.get('EventName') == 's3:ObjectCreated:Put'):
            LOGGER.debug('Storing data')
            key = str(message['Key'])
            filepath = f'{STORAGE_SOURCE}/{key}'
            if key.startswith(STORAGE_ARCHIVE):
                LOGGER.info(f'Do not process archived-data: {key}')
                return
        elif topic == 'wis2box/data_mappings/refresh':
            LOGGER.debug('Refresing data mappings')
            self.data_mappings = get_data_mappings()
            return
        elif topic == 'wis2box/dataset_publication':
            LOGGER.debug('Publishing dataset')
            metadata = message.get('somekey')
            discovery_metadata.publish_discovery_metadata(metadata)
            data_.add_collection_data(metadata)
            return
        elif topic.startswith('wis2box/dataset_unpublication'):
            LOGGER.debug('Unpublishing dataset')
            identifier = topic.split('/')[-1]
            remove_collection(identifier)
            return
        else:
            LOGGER.debug('Ignoring message')
            return

        while len(mp.active_children()) == mp.cpu_count():
            sleep(0.1)

        p = mp.Process(target=self.handle, args=(filepath, message))
        p.start()


@click.command()
@click.pass_context
@cli_helpers.OPTION_VERBOSITY
def subscribe(ctx, verbosity):
    """Subscribe to the internal broker and process incoming messages"""
    click.echo('Adding messages collection')
    setup_collection(meta=gcm())

    defs = {
        'codepath': PLUGINS['pubsub']['mqtt']['plugin'],
        'url': f'mqtt://{BROKER_USERNAME}:{BROKER_PASSWORD}@{BROKER_HOST}:{BROKER_PORT}',  # noqa
        'client_type': 'subscriber'
    }

    broker = load_plugin('pubsub', defs)

    # start the wis2box subscriber
    click.echo('Starting wis2box subscriber')
    WIS2BoxSubscriber(broker=broker)
