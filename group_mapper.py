import json
import logging
from typing import List, Tuple

import redis

logger = logging.getLogger("meraki_ise.group_mapper")


class GroupMapper:
    def __init__(self, config: dict, cache_expire: int = 28800):
        self.config = config
        self.redis = redis.Redis(host=config.get('redis_host', 'localhost'), port=config.get('redis_port', 6379),
                                 db=config.get('redis_db', 0))
        self.cache_expire = cache_expire
        self._profile_key = 'endpointProfile'

    def map_to_networkid(self, session: dict) -> str:
        raise NotImplementedError

    def map_to_groupid(self, session: dict) -> str:
        raise NotImplementedError

    def map(self, pxgrid_message: dict, name_key: str = 'userName', mac_key: str = 'macAddress') -> List[
        Tuple[str, str, str, str]]:
        """
        Do the mapping.

        :param pxgrid_message: Message from pxGrid
        :param name_key: Dictionary key for the username field in the pxGrid message
        :param mac_key: Dictionary key for the MAC address field in the pxGrid message
        :param group_key: Dictionary key for the group field in the pxGrid message
        :return: List of tuples of (network_id, mac, name, mapped_group)
        """

        mappings = []

        sessions = pxgrid_message.get('sessions')

        if sessions:
            # Messages can contain multiple sessions
            for session in sessions:
                # We're only interested in started and authenticated sessions
                if session['state'] not in ('STARTED', 'AUTHENTICATED'):
                    continue
                name = str(session[name_key])
                mac = str(session[mac_key])

                if len(session['ipAddresses']) == 0:
                    logger.error(f"Client {name} ({mac}) has no IP addresses. Cannot map to network.")
                    return []

                ip = session['ipAddresses'][0]

                # map the network and group IDs
                network_id = self.map_to_networkid(ip)
                logger.debug(f"Client {name} ({mac}) mapped to network {network_id}.")
                if self._profile_key in session:
                    # Do the heavy lifting
                    group_id = self.map_to_groupid(session)
                    result = (network_id, mac, name, group_id)
                    result_json_obj = json.dumps({'network_id': network_id, 'mac': mac, 'ip': ip, 'name': name, 'group': group_id})
                else:
                    logger.error(f"Client {name} ({mac}) has no {self._profile_key} set. Cannot map to group.")

                cached_mapping = self.redis.get(f"client.{mac.replace(':', '')}")

                if cached_mapping:
                    # We found a cached mapping. Nice.
                    # Now, if wanted the cached mapping to be acted upon (i.e. provision the client) uncomment the next
                    # two lines
                    #mapping = json.loads(cached_mapping)
                    #mappings.append((mapping['network_id'], mapping['mac'], mapping['name'], mapping['group']))
                    #need to check the string. if everything is the same, do nothing. But if any element is different do the other code
                    logger.debug(f"result_json_obj var is ({result_json_obj})")
                    logger.debug(f"cached_mapping var is ({cached_mapping})")
                    if cached_mapping.decode() == result_json_obj:
                        logger.debug(f"Found a cached identical mapping for client {name} ({mac})")
                    else:
                        logger.debug(f"Found a cached but different mapping for client {name} ({mac})")
                        # so let's update it then
                        json_obj = json.dumps({'network_id': network_id, 'mac': mac, 'ip': ip, 'name': name, 'group': group_id})
                        self.redis.set(f"client.{mac.replace(':', '')}", json_obj, ex=self.cache_expire)
                        mappings.append(result)
                else:
                    json_obj = json.dumps({'network_id': network_id, 'mac': mac, 'ip': ip, 'name': name, 'group': group_id})
                    self.redis.set(f"client.{mac.replace(':', '')}", json_obj, ex=self.cache_expire)
                    mappings.append(result)
        else:
            logger.debug(f"Mapper called with an empty session object. Doing nothing.")

        # If the message did not contain session information this will return an empty list
        return mappings
