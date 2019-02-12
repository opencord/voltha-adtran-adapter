#
# Copyright 2017 the original author or authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""
Adtran ONU adapter.
"""
import structlog
import binascii
from pyvoltha.adapters.iadapter import OnuAdapter
from pyvoltha.protos import third_party
from adtran_onu_handler import AdtranOnuHandler
from pyvoltha.adapters.extensions.omci.openomci_agent import OpenOMCIAgent, OpenOmciAgentDefaults
from omci.adtn_capabilities_task import AdtnCapabilitiesTask
from omci.adtn_get_mds_task import AdtnGetMdsTask
from omci.adtn_mib_sync import AdtnMibSynchronizer
from omci.adtn_mib_resync_task import AdtnMibResyncTask
from omci.adtn_mib_reconcile_task import AdtnMibReconcileTask
from copy import deepcopy

_ = third_party


class AdtranOnuAdapter(OnuAdapter):
    def __init__(self, core_proxy, adapter_proxy, config):
        self.log = structlog.get_logger()
        super(AdtranOnuAdapter, self).__init__(core_proxy=core_proxy,
                                               adapter_proxy=adapter_proxy,
                                               config=config,
                                               device_handler_class=AdtranOnuHandler,
                                               name='adtran_onu',
                                               vendor='ADTRAN, Inc.',
                                               version='2.0',
                                               device_type='adtran_onu',
                                               vendor_id='ADTN',
                                               accepts_bulk_flow_update=True,
                                               accepts_add_remove_flow_updates=False)  # TODO: Support flow-mods
        # Customize OpenOMCI for Adtran ONUs
        self.adtran_omci = deepcopy(OpenOmciAgentDefaults)

        from pyvoltha.adapters.extensions.omci.database.mib_db_dict import MibDbVolatileDict
        self.adtran_omci['mib-synchronizer']['database'] = MibDbVolatileDict

        self.adtran_omci['mib-synchronizer']['state-machine'] = AdtnMibSynchronizer
        self.adtran_omci['mib-synchronizer']['tasks']['get-mds'] = AdtnGetMdsTask
        self.adtran_omci['mib-synchronizer']['tasks']['mib-audit'] = AdtnGetMdsTask
        self.adtran_omci['mib-synchronizer']['tasks']['mib-resync'] = AdtnMibResyncTask
        self.adtran_omci['mib-synchronizer']['tasks']['mib-reconcile'] = AdtnMibReconcileTask
        self.adtran_omci['omci-capabilities']['tasks']['get-capabilities'] = AdtnCapabilitiesTask
        # TODO: Continue to customize adtran_omci here as needed

        self._omci_agent = OpenOMCIAgent(self.adapter_agent.core,
                                         support_classes=self.adtran_omci)

    @property
    def omci_agent(self):
        return self._omci_agent

    def start(self):
        super(AdtranOnuAdapter, self).start()
        self._omci_agent.start()

    def stop(self):
        omci, self._omci_agent = self._omci_agent, None
        if omci is not None:
            omci.stop()

        super(AdtranOnuAdapter, self).stop()

    def download_image(self, device, request):
        raise NotImplementedError()

    def activate_image_update(self, device, request):
        raise NotImplementedError()

    def cancel_image_download(self, device, request):
        raise NotImplementedError()

    def revert_image_update(self, device, request):
        raise NotImplementedError()

    def get_image_download_status(self, device, request):
        raise NotImplementedError()

    def process_inter_adapter_message(self, msg):
        # Currently the only OLT Device adapter that uses this is the EdgeCore

        self.log.info('receive_inter_adapter_message', msg=msg)
        proxy_address = msg['proxy_address']
        assert proxy_address is not None
        # Device_id from the proxy_address is the olt device id. We need to
        # get the onu device id using the port number in the proxy_address
        device = self.adapter_agent.get_child_device_with_proxy_address(proxy_address)
        if device is not None:
            handler = self.devices_handlers[device.id]
            handler.event_messages.put(msg)
        else:
            self.log.error("device-not-found")

    def receive_proxied_message(self, proxy_address, msg):
        self.log.debug('receive-proxied-message', proxy_address=proxy_address,
                       device_id=proxy_address.device_id, msg=binascii.hexlify(msg))
        # Device_id from the proxy_address is the olt device id. We need to
        # get the onu device id using the port number in the proxy_address
        device = self.adapter_agent.get_child_device_with_proxy_address(proxy_address)

        if device is not None:
            handler = self.devices_handlers[device.id]
            if handler is not None:
                handler.receive_message(msg)
