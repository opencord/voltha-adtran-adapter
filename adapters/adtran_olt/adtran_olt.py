#
# Copyright 2019-present ADTRAN, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""
ADTRAN OLT Adapter.
"""
import structlog
from twisted.internet import reactor, defer

from pyvoltha.adapters.iadapter import OltAdapter
from pyvoltha.protos import third_party
from pyvoltha.protos.common_pb2 import AdminState

from adtran_olt_handler import AdtranOltHandler


_ = third_party
log = structlog.get_logger()


class AdtranOltAdapter(OltAdapter):
    name = 'adtran_olt'

    def __init__(self, core_proxy, adapter_proxy, config):
        super(AdtranOltAdapter, self).__init__(core_proxy=core_proxy,
                                               adapter_proxy=adapter_proxy,
                                               config=config,
                                               device_handler_class=AdtranOltHandler,
                                               name=AdtranOltAdapter.name,
                                               vendor='ADTRAN, Inc.',
                                               version='2.0.0',
                                               device_type=AdtranOltAdapter.name,
                                               accepts_bulk_flow_update=True,
                                               accepts_add_remove_flow_updates=False)  # TODO: Implement me

        log.debug('adtran_olt.__init__')

    def health(self):
        """
        Return a 3-state health status using the voltha.HealthStatus message.

        :return: Deferred or direct return with voltha.HealthStatus message
        """
        # TODO: Currently this is always healthy for every adapter.
        #       If we decide not to modify this, delete this method and use base class method
        from pyvoltha.protos.health_pb2 import HealthStatus
        return HealthStatus(state=HealthStatus.HEALTHY)

    def abandon_device(self, device):
        """
        Make sure the adapter no longer looks after device. This is called
        if device ownership is taken over by another Voltha instance.

        :param device: A Voltha.Device object
        :return: (Deferred) Shall be fired to acknowledge abandonment.
        """
        log.info('abandon-device', device=device)
        raise NotImplementedError()

    def adopt_device(self, device):
        """
        Make sure the adapter looks after given device. Called when a device
        is provisioned top-down and needs to be activated by the adapter.

        :param device: A voltha.Device object, with possible device-type
                specific extensions. Such extensions shall be described as part of
                the device type specification returned by device_types().
        :return: (Deferred) Shall be fired to acknowledge device ownership.
        """
        log.info('adopt-device', device=device)
        kwargs = {
            'adapter': self,
            'device-id': device.id
        }
        self.devices_handlers[device.id] = self.device_handler_class(**kwargs)
        d = defer.Deferred()
        reactor.callLater(0, self.devices_handlers[device.id].activate, d, False)
        return d

    def reconcile_device(self, device):
        try:
            self.devices_handlers[device.id] = self.device_handler_class(self,
                                                                         device.id)
            # Work only required for devices that are in ENABLED state
            if device.admin_state == AdminState.ENABLED:

                kwargs = {
                    'adapter': self,
                    'device-id': device.id
                }
                self.devices_handlers[device.id] =self.device_handler_class(**kwargs)
                d = defer.Deferred()
                reactor.callLater(0, self.devices_handlers[device.id].activate, d, True)

            else:
                # Invoke the children reconciliation which would setup the
                # basic children data structures
                self.core_proxy.reconcile_child_devices(device.id)
            return device

        except Exception, e:
            log.exception('Exception', e=e)

    def self_test_device(self, device):
        """
        This is called to Self a device based on a NBI call.
        :param device: A Voltha.Device object.
        :return: Will return result of self test
        """
        log.info('self-test-device', device=device.id)
        # TODO: Support self test?
        from pyvoltha.protos.voltha_pb2 import SelfTestResponse
        return SelfTestResponse(result=SelfTestResponse.NOT_SUPPORTED)

    def delete_device(self, device):
        """
        This is called to delete a device from the PON based on a NBI call.
        If the device is an OLT then the whole PON will be deleted.

        :param device: A Voltha.Device object.
        :return: (Deferred) Shall be fired to acknowledge the deletion.
        """
        log.info('delete-device', device=device)
        handler = self.devices_handlers.get(device.id)
        if handler is not None:
            reactor.callLater(0, handler.delete)
            del self.device_handlers[device.id]
            del self.logical_device_id_to_root_device_id[device.parent_id]

        return device

    def download_image(self, device, request):
        """
        This is called to request downloading a specified image into the standby partition
        of a device based on a NBI call.

        :param device: A Voltha.Device object.
        :param request: A Voltha.ImageDownload object.
        :return: (Deferred) Shall be fired to acknowledge the download.
        """
        log.info('image_download', device=device, request=request)
        handler = self.devices_handlers.get(device.id)
        if handler is not None:
            return handler.start_download(device, request, defer.Deferred())

    def get_image_download_status(self, device, request):
        """
        This is called to inquire about a requested image download status based
        on a NBI call. The adapter is expected to update the DownloadImage DB object
        with the query result

        :param device: A Voltha.Device object.
        :param request: A Voltha.ImageDownload object.
        :return: (Deferred) Shall be fired to acknowledge
        """
        log.info('get_image_download', device=device, request=request)
        handler = self.devices_handlers.get(device.id)
        if handler is not None:
            return handler.download_status(device, request, defer.Deferred())

    def cancel_image_download(self, device, request):
        """
        This is called to cancel a requested image download
        based on a NBI call.  The admin state of the device will not
        change after the download.
        :param device: A Voltha.Device object.
        :param request: A Voltha.ImageDownload object.
        :return: (Deferred) Shall be fired to acknowledge
        """
        log.info('cancel_image_download', device=device)
        handler = self.devices_handlers.get(device.id)
        if handler is not None:
            return handler.cancel_download(device, request, defer.Deferred())

    def activate_image_update(self, device, request):
        """
        This is called to activate a downloaded image from
        a standby partition into active partition.
        Depending on the device implementation, this call
        may or may not cause device reboot.
        If no reboot, then a reboot is required to make the
        activated image running on device
        This call is expected to be non-blocking.
        :param device: A Voltha.Device object.
        :param request: A Voltha.ImageDownload object.
        :return: (Deferred) OperationResponse object.
        """
        log.info('activate_image_update', device=device, request=request)
        handler = self.devices_handlers.get(device.id)
        if handler is not None:
            return handler.activate_image(device, request, defer.Deferred())

    def revert_image_update(self, device, request):
        """
        This is called to deactivate the specified image at
        active partition, and revert to previous image at
        standby partition.
        Depending on the device implementation, this call
        may or may not cause device reboot.
        If no reboot, then a reboot is required to make the
        previous image running on device
        This call is expected to be non-blocking.
        :param device: A Voltha.Device object.
        :param request: A Voltha.ImageDownload object.
        :return: (Deferred) OperationResponse object.
        """
        log.info('revert_image_update', device=device, request=request)
        handler = self.devices_handlers.get(device.id)
        if handler is not None:
            return handler.revert_image(device, request, defer.Deferred())
