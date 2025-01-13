#!/usr/bin/env python3
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

import argparse
import os
import re
import requests
import subprocess
import shutil


if subprocess.call(['docker', 'compose'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) > 0:
    DOCKER_COMPOSE_COMMAND = 'docker-compose'
else:
    DOCKER_COMPOSE_COMMAND = 'docker compose'

DOCKER_COMPOSE_ARGS = """
    --file docker-compose.yml
    --file docker-compose.override.yml
    --file docker-compose.monitoring.yml
    --env-file wis2box.env
    --project-name wis2box_project
    """

parser = argparse.ArgumentParser(
    description='Manage a composition of Docker containers to implement wis2box',
    formatter_class=argparse.RawTextHelpFormatter
)

parser.add_argument('--simulate',
                    action='store_true',
                    help='Simulate execution by printing action rather than executing')

commands = [
    'build',
    'config',
    'execute',
    'lint',
    'logs',
    'login',
    'prune',
    'restart',
    'start',
    'start-dev',
    'status',
    'stop',
    'update',
    'update-local-build',
    'update-latest-tags'
]

parser.add_argument('command',
                    choices=commands,
                    help="""The command to execute:
    - config: validate and view Docker configuration
    - build: build all services
    - start: start system
    - start-dev: start system in local development mode
    - login: login to the container (default: wis2box-management)
    - stop: stop system
    - update: update Docker images
    - prune: cleanup dangling containers and images
    - restart: restart containers
    - status: view status of wis2box containers
    - lint: run PEP8 checks against local Python code
    """)

parser.add_argument('args', nargs=argparse.REMAINDER, help='Additional arguments for the command')

args = parser.parse_args()

LOCAL_IMAGES = [
    'wis2box-management',
    'wis2box-broker',
    'wis2box-mqtt-metrics-collector'
]

def remove_docker_images(filter: str) -> None:
    # Get the IDs of images matching the filter
    result = subprocess.run(
        ['docker', 'images', '--filter', f'reference={filter}', '-q', '--no-trunc'],
        capture_output=True,
        text=True
    )
    
    image_ids = result.stdout.strip()
    if image_ids:  # If there are images to remove
        for image_id in image_ids.splitlines():
            try:
                subprocess.run(['docker', 'rmi', image_id], check=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            except subprocess.CalledProcessError as e:
                # do nothing
                pass

def build_local_images() -> None:
    """
    Build local images

    :returns: None.
    """
    for image in LOCAL_IMAGES:
        print(f'Building {image}')
        run(split(f'docker build -t wmoim/{image}:local {image}'))

    return None

def get_latest_image_tag(image: str) -> str:
    """
    list image tags by querying docker hub api
    skip the 'latest' tag
    return the most recent tag

    :param image: required, string. Name of the image.

    :returns: string. The most recent tag.
    """

    url = f"https://hub.docker.com/v2/repositories/wmoim/{image}/tags/"
    tags = []
    try:
        # Paginate through results to collect all tags
        while url:
            response = requests.get(url)
            response.raise_for_status()  # Raise an error for HTTP failures
            data = response.json()
            tags.extend([
                tag['name'] for tag in data.get('results', [])
                if tag['name'] != 'latest'  # Skip 'latest' tag
            ])
            url = data.get('next')  # Get the next page URL
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to fetch tags for image '{image}': {e}")

    if not tags:
        raise ValueError(f"No valid tags found for image '{image}'")
    else:
        print(f"Found {len(tags)} tags for image '{image}: {tags}'")

    # define a function to sort tags by version number
    def tag_sort_key(tag):
        # Extract numeric and non-numeric parts
        parts = re.split(r'(\d+)', tag)  # Split into numeric and non-numeric segments
        return [
            int(part) if part.isdigit() else 'ZZZZZZZZZZ'  # Use a large number for non-numeric parts
            for part in parts
        ]

    # Sort tags by version number in descending order
    tags.sort(key=tag_sort_key, reverse=True)
    return tags[0]
    

def update_docker_images(use_local_build: bool = False, use_latest: bool = False) -> None:
    """
    Write docker-compose.yml using docker-compose.base.yml as base
    

    use_local_build: required, boolean. If True, build local images
    use_tags: required, boolean. If True, pull last tagged release for image. If False, use local images or tag='latest' # noqa
    
    :returns: None.
    """
    
    if os.path.exists('docker-compose.yml'):
        print('Backing up current docker-compose.yml to docker-compose.yml.bak')
        shutil.copy('docker-compose.yml', 'docker-compose.yml.bak')

    if use_local_build:
        print('Building local images')
        build_local_images()

    print('Updating docker-compose.yml')

    with open('docker-compose.base.yml', 'r') as f:
        lines = f.readlines()
        with open('docker-compose.yml', 'w') as f:
            for line in lines:
                if 'image: wmoim/' in line:
                    image = line.split('wmoim/')[1].split(':')[0]
                    
                    # determine the tag to use
                    tag = 'latest'
                    if image in LOCAL_IMAGES and use_local_build:
                        tag = 'local'
                    elif image not in LOCAL_IMAGES and use_local_build:
                        tag = 'latest'
                    elif not use_latest:
                        print(f'Get latest image tag for {image}')
                        tag = get_latest_image_tag(image)
                    
                    # pull the image if it is not local, o
                    if tag != 'local':
                        print(f'Pulling wmoim/{image}:{tag}')
                        # pull the latest tag for the image
                        run(split(f'docker pull wmoim/{image}:{tag}'))
                    
                    # update the image tag in the docker-compose.yml
                    print(f'Set {image} to {tag}')
                    f.write(f'    image: wmoim/{image}:{tag}\n')
                else:
                    f.write(line)
        print('docker-compose.yml updated')
        return None

def split(value: str) -> list:
    """
    Splits string and returns as list

    :param value: required, string. bash command.

    :returns: list. List of separated arguments.
    """
    return value.split()


def find_files(path: str, extension: str) -> list:
    """
    Walks directory path collecting all files of a given extention.

    :param path: `str` of directory path
    :param extension: `str` of file extension

    :returns: `list` of Python filepaths
    """

    file_list = []
    for root, _, files in os.walk(path, topdown=False):
        for name in files:
            if name.endswith(extension):
                file_list.append(os.path.join(root, name))

    return file_list


def run(cmd, silence_stderr=False) -> None:

    if not silence_stderr:
        subprocess.run(cmd)
    else:
        subprocess.run(cmd, stderr=subprocess.DEVNULL)

    return None


def make(args) -> None:
    """
    Serves as pseudo Makefile using Python subprocesses.

    :param command: required, string. Make command.

    :returns: None.
    """

    if not os.path.exists('wis2box.env'):
        print("ERROR: wis2box.env file does not exist.  Please create one manually or by running `python3 wis2box-create-config.py`")
        exit(1)
    # check if WIS2BOX_SSL_KEY and WIS2BOX_SSL_CERT are set
    ssl_key = None
    ssl_cert = None
    with open('wis2box.env', 'r') as f:
        for line in f:
            if 'WIS2BOX_SSL_KEY' in line:
                ssl_key = line.split('=')[1].strip()
            if 'WIS2BOX_SSL_CERT' in line:
                ssl_cert = line.split('=')[1].strip()
    docker_compose_args = DOCKER_COMPOSE_ARGS
    if (ssl_key and ssl_cert):
        docker_compose_args +=" --file docker-compose.ssl.yml"
    # if you selected a bunch of them, default to all
    containers = "" if not args.args else ' '.join(args.args)

    # if there can be only one, default to wisbox
    container = "wis2box-management" if not args.args else ' '.join(args.args)

    if args.command == "config":
        run(split(f'{DOCKER_COMPOSE_COMMAND} {docker_compose_args} config'))
    elif args.command in ["up", "start", "start-dev"]:
        if not os.path.exists('docker-compose.yml'):
            update_docker_images()
        run(split(
            'docker plugin install grafana/loki-docker-driver:latest --alias loki --grant-all-permissions'),
            silence_stderr=True)
        run(split('docker plugin enable loki'), silence_stderr=True)
        if containers:
            run(split(f"{DOCKER_COMPOSE_COMMAND} {docker_compose_args} start {containers}"))
        else:
            if args.command == 'start-dev':
                run(split(f'{DOCKER_COMPOSE_COMMAND} {docker_compose_args} --file docker-compose.dev.yml up -d'))
            else:
                run(split(f'{DOCKER_COMPOSE_COMMAND} {docker_compose_args} up -d'))
    elif args.command in ["update", "update-local-build", "update-latest-tags"]:
        if args.command == "update-local-build":
            update_docker_images(use_local_build=True)
        elif args.command == "update-use-latest":
            update_docker_images(use_local_build=False, use_latest=True)
        else:
            update_docker_images()
        # restart all containers
        run(split(
                f'{DOCKER_COMPOSE_COMMAND} {docker_compose_args} down --remove-orphans'))
        run(split(
                f'{DOCKER_COMPOSE_COMMAND} {docker_compose_args} up -d'))
        # perform cleanup of images after update, unless updating local build
        if not args.command == "update-local-build":
            remove_docker_images('wmoim/wis2*')
            remove_docker_images('ghcr.io/wmo-im/wis2*')
    elif args.command == "execute":
        run(['docker', 'exec', '-i', 'wis2box-management', 'sh', '-c', containers])
    elif args.command == "login":
        run(split(f'docker exec -it {container} /bin/bash'))
    elif args.command == "login-root":
        run(split(f'docker exec -u -0 -it {container} /bin/bash'))
    elif args.command == "logs":
        run(split(
            f'{DOCKER_COMPOSE_COMMAND} {docker_compose_args} logs --follow {containers}'))
    elif args.command in ["stop", "down"]:
        if containers:
            run(split(f"{DOCKER_COMPOSE_COMMAND} {docker_compose_args} {containers}"))
        else:
            run(split(
                f'{DOCKER_COMPOSE_COMMAND} {docker_compose_args} down --remove-orphans {containers}'))
    elif args.command == "prune":
        run(split('docker builder prune -f'))
        run(split('docker container prune -f'))
        run( split('docker volume prune -f'))
        # prune any unused images starting with wmoim/wis2
        remove_docker_images('wmoim/wis2*')
        # prune any unused images starting with ghcr.io/wmo-im/wis2
        remove_docker_images('ghcr.io/wmo-im/wis2*')
    elif args.command == "restart":
        if containers:
            run(split(
                f'{DOCKER_COMPOSE_COMMAND} {docker_compose_args} stop {containers}'))
            run(split(
                f'{DOCKER_COMPOSE_COMMAND} {docker_compose_args} start {containers}'))
        else:
            run(split(
                f'{DOCKER_COMPOSE_COMMAND} {docker_compose_args} down --remove-orphans'))
            run(split(
                f'{DOCKER_COMPOSE_COMMAND} {docker_compose_args} up -d'))
    elif args.command == "status":
        run(split(
            f'{DOCKER_COMPOSE_COMMAND} {docker_compose_args} ps {containers}'))
    elif args.command == "lint":
        files = find_files(".", '.py')
        run(('python3', '-m', 'flake8', *files))


if __name__ == "__main__":
    make(args)
