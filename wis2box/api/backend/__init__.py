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

import logging
from typing import Any

from wis2box.env import API_BACKEND_TYPE, API_BACKEND_URL
from wis2box.plugin import load_plugin, PLUGINS

LOGGER = logging.getLogger(__name__)


def load_backend() -> Any:
    """
    Load wis2box API backend

    :returns: plugin object
    """

    LOGGER.debug('Loading backend')

    codepath = PLUGINS['api_backend'][API_BACKEND_TYPE]['plugin']
    defs = {
        'codepath': codepath,
        'url': API_BACKEND_URL
    }

    return load_plugin('api_backend', defs)
