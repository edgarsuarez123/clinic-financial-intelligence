from unittest.mock import Mock
from app.ingestion.worker import process_queues


def test_financial_failure_does_not_starve_appointment_imports_or_log_payloads():
    financial = Mock()
    financial.process_one.side_effect = ValueError('private payload')
    appointments = Mock()
    appointments.process_one.return_value = True
    logger = Mock()
    assert process_queues([('ingestion', financial), ('appointments', appointments)], logger) == (True, True)
    appointments.process_one.assert_called_once_with()
    assert 'private payload' not in str(logger.mock_calls)


def test_busy_financial_queue_still_processes_appointments():
    financial, appointments = Mock(), Mock()
    financial.process_one.return_value = True
    appointments.process_one.return_value = False
    assert process_queues([('ingestion', financial), ('appointments', appointments)], Mock()) == (True, False)
    appointments.process_one.assert_called_once_with()
