"""
Copyright 2017-present, Airbnb Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
import os

from mock import ANY, call, MagicMock, Mock, patch
from nose.tools import (
    assert_equal,
    assert_false,
    assert_is_instance,
    assert_is_none,
    assert_true
)

from stream_alert.alert_processor.main import AlertProcessor, handler
from stream_alert.alert_processor.outputs.output_base import OutputDispatcher
from stream_alert.shared import NORMALIZATION_KEY
from stream_alert.shared.alert import Alert
from stream_alert.shared.config import load_config
from tests.unit.stream_alert_alert_processor import (
    ACCOUNT_ID, ALERTS_TABLE, FUNCTION_NAME, PREFIX, REGION)

_ARN = 'arn:aws:lambda:{}:{}:function:{}:production'.format(REGION, ACCOUNT_ID, FUNCTION_NAME)


@patch.dict(os.environ, {'AWS_DEFAULT_REGION': 'us-east-1'})
class TestAlertProcessor(object):
    """Tests for alert_processor/main.py"""
    # pylint: disable=no-member,no-self-use,protected-access

    @patch('stream_alert.alert_processor.main.load_config',
           Mock(return_value=load_config('tests/unit/conf/', validate=True)))
    @patch.dict(os.environ, {'ALERTS_TABLE': ALERTS_TABLE})
    @patch.object(AlertProcessor, 'BACKOFF_MAX_TRIES', 1)
    @patch('stream_alert.alert_processor.main.AlertTable', MagicMock())
    def setup(self):
        """Alert Processor - Test Setup"""
        # pylint: disable=attribute-defined-outside-init
        self.processor = AlertProcessor(_ARN)
        self.alert = Alert(
            'hello_world',
            {'abc': 123, NORMALIZATION_KEY: {}},
            {'slack:unit-test-channel'}
        )

    def test_init(self):
        """Alert Processor - Initialization"""
        assert_is_instance(self.processor.config, dict)
        assert_equal(self.processor.region, REGION)
        assert_equal(self.processor.account_id, ACCOUNT_ID)
        assert_equal(self.processor.prefix, PREFIX)

    @patch('stream_alert.alert_processor.main.LOGGER')
    def test_create_dispatcher_invalid(self, mock_logger):
        """Alert Processor - Create Dispatcher - Invalid Output"""
        assert_is_none(self.processor._create_dispatcher('helloworld'))
        mock_logger.error.called_once_with(ANY, 'helloworld')

    @patch('stream_alert.alert_processor.main.LOGGER')
    def test_create_dispatcher_output_doesnt_exist(self, mock_logger):
        """Alert Processor - Create Dispatcher - Output Does Not Exist"""
        assert_is_none(self.processor._create_dispatcher('slack:no-such-channel'))
        mock_logger.error.called_once_with(
            'The output \'%s\' does not exist!', 'slack:no-such-channel')

    def test_create_dispatcher(self):
        """Alert Processor - Create Dispatcher - Success"""
        dispatcher = self.processor._create_dispatcher('aws-s3:unit_test_bucket')
        assert_is_instance(dispatcher, OutputDispatcher)

    @patch('stream_alert.alert_processor.main.LOGGER')
    def test_send_alert_exception(self, mock_logger):
        """Alert Processor - Send Alert - Exception"""
        dispatcher = MagicMock()
        dispatcher.dispatch.side_effect = AttributeError
        alert = Alert('hello_world', {'abc': 123}, {'output'})
        output = 'slack:unit_test_channel'

        assert_false(AlertProcessor._send_alert(alert, output, dispatcher))
        mock_logger.assert_has_calls([
            call.info('Sending %s to %s', alert, output),
            call.exception('Exception when sending %s to %s. Alert:\n%s', alert, output, ANY)
        ])

    @patch('stream_alert.alert_processor.main.LOGGER')
    def test_send_alert(self, mock_logger):
        """Alert Processor - Send Alert - Success"""
        dispatcher = MagicMock()
        dispatcher.dispatch.return_value = True
        output = 'slack:unit_test_channel'

        assert_true(AlertProcessor._send_alert(self.alert, output, dispatcher))
        mock_logger.info.assert_called_once_with('Sending %s to %s', self.alert, output)
        dispatcher.dispatch.assert_called_once_with(self.alert, 'unit_test_channel')

    @patch.object(AlertProcessor, '_create_dispatcher')
    @patch.object(AlertProcessor, '_send_alert', return_value=True)
    def test_send_alerts_success(self, mock_send_alert, mock_create_dispatcher):
        """Alert Processor - Send Alerts Success"""
        result = self.processor._send_to_outputs(self.alert)
        mock_create_dispatcher.assert_called_once()
        mock_send_alert.assert_called_once()
        assert_equal({'slack:unit-test-channel': True}, result)
        assert_equal(self.alert.outputs, self.alert.outputs_sent)

    @patch.object(AlertProcessor, '_create_dispatcher')
    @patch.object(AlertProcessor, '_send_alert', return_value=False)
    def test_send_alerts_failure(self, mock_send_alert, mock_create_dispatcher):
        """Alert Processor - Send Alerts Failure"""
        result = self.processor._send_to_outputs(self.alert)
        mock_create_dispatcher.assert_called_once()
        mock_send_alert.assert_called_once()
        assert_equal({'slack:unit-test-channel': False}, result)
        assert_equal(set(), self.alert.outputs_sent)

    @patch.object(AlertProcessor, '_create_dispatcher', return_value=None)
    def test_send_alerts_skip_invalid_outputs(self, mock_create_dispatcher):
        """Alert Processor - Send Alerts With Invalid Outputs"""
        result = self.processor._send_to_outputs(self.alert)
        mock_create_dispatcher.assert_called_once()
        assert_equal({'slack:unit-test-channel': False}, result)

    def test_update_alerts_table_none(self):
        """Alert Processor - Update Alerts Table - Empty Results"""
        self.processor.alerts_table.delete_alert = MagicMock()
        self.processor.alerts_table.update_retry_outputs = MagicMock()
        self.processor._update_table(self.alert, {})
        self.processor.alerts_table.delete_alert.assert_not_called()
        self.processor.alerts_table.update_retry_outputs.assert_not_called()

    def test_update_alerts_table_delete(self):
        """Alert Processor - Update Alerts Table - Delete Item"""
        self.processor._update_table(self.alert, {'out1': True, 'out2': True})
        self.processor.alerts_table.delete_alerts.assert_called_once_with(
            [(self.alert.rule_name, self.alert.alert_id)])

    def test_update_alerts_table_update(self):
        """Alert Processor - Update Alerts Table - Update With Failed Outputs"""
        self.processor._update_table(self.alert, {'out1': True, 'out2': False, 'out3': False})
        self.processor.alerts_table.update_sent_outputs.assert_called_once_with(self.alert)

    @patch.object(AlertProcessor, '_send_to_outputs',
                  return_value={'slack:unit-test-channel': True})
    @patch.object(AlertProcessor, '_update_table')
    def test_run_full_event(self, mock_send_alerts, mock_update_table):
        """Alert Processor - Run With the Full Alert Record"""
        result = self.processor.run(self.alert.dynamo_record())
        assert_equal({'slack:unit-test-channel': True}, result)
        mock_send_alerts.assert_called_once()
        mock_update_table.assert_called_once()

    @patch('stream_alert.alert_processor.main.LOGGER')
    def test_run_invalid_alert(self, mock_logger):
        """Alert Processor - Run With an Invalid Alert"""
        result = self.processor.run({'Record': 'Nonsense'})
        assert_equal({}, result)
        mock_logger.exception.called_once_with('Invalid alert %s', {'Record': 'Nonsense'})

    @patch.object(AlertProcessor, '_send_to_outputs',
                  return_value={'slack:unit-test-channel': True})
    @patch.object(AlertProcessor, '_update_table')
    def test_run_get_alert_from_dynamo(self, mock_send_alerts, mock_update_table):
        """Alert Processor - Run With Just the Alert Key"""
        self.processor.alerts_table.get_alert_record = MagicMock(
            return_value=self.alert.dynamo_record())
        result = self.processor.run(self.alert.dynamo_key)
        assert_equal({'slack:unit-test-channel': True}, result)

        self.processor.alerts_table.get_alert_record.assert_called_once_with(
            self.alert.rule_name, self.alert.alert_id)
        mock_send_alerts.assert_called_once()
        mock_update_table.assert_called_once()

    @patch('stream_alert.alert_processor.main.LOGGER')
    def test_run_alert_does_not_exist(self, mock_logger):
        """Alert Processor - Run - Alert Does Not Exist"""
        self.processor.alerts_table.get_alert_record = MagicMock(return_value=None)
        self.processor.run(self.alert.dynamo_key)
        mock_logger.error.assert_called_once_with(
            '%s does not exist in the alerts table', self.alert.dynamo_key)

    @patch.dict(os.environ, {'ALERTS_TABLE': ALERTS_TABLE})
    @patch.object(AlertProcessor, 'run', return_value={'output': True})
    def test_handler(self, mock_run):
        """Alert Processor - Lambda Handler"""
        context = MagicMock()
        context.invoked_function_arn = _ARN
        event = {'AlertID': 'abc', 'RuleName': 'hello_world'}
        result = handler(event, context)
        assert_equal({'output': True}, result)
        mock_run.assert_called_once_with(event)
