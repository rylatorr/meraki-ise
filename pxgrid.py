# author: Felix Kaechele <fkaechel@cisco.com>

import json
import logging
import ssl

import backoff
import requests
from requests.auth import HTTPBasicAuth

from ws_stomp import WebSocketStomp

__author__ = "Felix Kaechele"
__email__ = "fkaechel@cisco.com"
__copyright__ = "Copyright (c) 2020 Cisco and/or its affiliates"
__license__ = "Cisco Sample Code License"

class PxgridConfig:
    def __init__(self, config: map):
        self.host = config['pxgrid_host']
        self.nodename = config['pxgrid_nodename']
        self.password = config['pxgrid_password']
        self.description = config['pxgrid_description']
        self.client_cert = config['pxgrid_client_cert']
        self.client_key = config['pxgrid_client_key']
        self.ca_cert = config['pxgrid_ca_cert']
        self.ca_verify = config['pxgrid_ca_verify']


class PxgridRest:

    def __init__(self, config: PxgridConfig):
        self.account_active = False
        self.config = config
        self.base_url = f"https://{self.config.host}:8910/pxgrid/control/"

    @backoff.on_predicate(backoff.fibo, max_tries=10)
    def _account_activate(self):
        r = self._account_activate_request()
        if 'accountState' in r:
            self.account_active = r['accountState'] == 'ENABLED'

        return self.account_active

    def _account_activate_request(self):
        payload = {}
        if self.config.description:
            payload['description'] = self.config.description
        return self.request('AccountActivate', payload, False)

    def request(self, endpoint, payload, require_active_account=True):
        if not self.account_active and require_active_account:
            self.account_active = self._account_activate()
        url = self.base_url + endpoint
        logging.debug(f"pxgrid url={url}")
        json_string = json.dumps(payload)
        logging.debug(f"  request={json_string}")
        if self.config.client_cert:
            r = requests.post(url,
                              auth=HTTPBasicAuth(self.config.nodename, ''),
                              cert=(self.config.client_cert, self.config.client_key),
                              json=payload,
                              verify=self.config.ca_cert if self.config.ca_verify else False)
        else:
            r = requests.post(url,
                              auth=HTTPBasicAuth(self.config.nodename, self.config.password),
                              verify=self.config.ca_cert if self.config.ca_verify else False)

        response = {}
        try:
            response = r.json()
        except json.decoder.JSONDecodeError:
            pass

        logging.debug(f"  response={response}")
        return response


class PxgridService(PxgridRest):

    def __init__(self, config: PxgridConfig, service_name: str):
        super().__init__(config)
        lookup_result = self._lookup(service_name)
        self.name = lookup_result['name']
        self.node_name = lookup_result['nodeName']
        self.properties = lookup_result['properties']

    def _lookup(self, service_name):
        payload = {'name': service_name}
        service_lookup_response = self.request('ServiceLookup', payload)
        return service_lookup_response['services'][0]

    def get_access_secret(self):
        payload = {'peerNodeName': self.node_name}
        return self.request('AccessSecret', payload)['secret']


class PxgridSessionService(PxgridService):
    def __init__(self, config: PxgridConfig):
        super().__init__(config, 'com.cisco.ise.session')
        self.base_url = self.properties['restBaseUrl'] + '/'

    def get_user_groups_by_username(self, username):
        payload = {'userName': username}
        return self.request('getUserGroupByUserName', payload)['groups']


class PxgridSessionPubsub(WebSocketStomp):

    def __init__(self, session_service: PxgridSessionService):
        self.config = session_service.config
        self.__session_service = session_service
        self.__session_pubsub_service = PxgridService(self.config,
                                                      self.__session_service.properties['wsPubsubService'])
        super().__init__(self.__session_pubsub_service.properties['wsUrl'],
                         self.config.nodename,
                         self.__session_pubsub_service.get_access_secret(),
                         self._create_ssl_context())

    async def connect(self):
        await super().connect()
        await self.stomp_connect(self.__session_pubsub_service.node_name)
        await self.stomp_subscribe(self.__session_service.properties['sessionTopic'])

    def _create_ssl_context(self):
        #context = ssl.create_default_context()
        context = ssl._create_unverified_context()
        if self.config.client_cert:
            context.load_cert_chain(certfile=self.config.client_cert,
                                    keyfile=self.config.client_key)
        context.load_verify_locations(cafile=self.config.ca_cert)
        return context

    async def read_message(self):
        message = await self.stomp_read_message()
        return json.loads(message)
