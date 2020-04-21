# flake8: noqa: W293
import textwrap
from unittest.mock import Mock

from ..notifications import notify_rpki_invalid_owners
from irrd.utils.test_utils import flatten_mock_calls
from irrd.storage.database_handler import DatabaseHandler
from irrd.utils.rpsl_samples import SAMPLE_ROUTE, SAMPLE_ROUTE6
from ..status import RPKIStatus
from ...storage.queries import RPSLDatabaseQuery
from ...utils.email import send_email


class TestNotifyRPKIInvalidOwners:
    def test_notify_regular(self, monkeypatch, config_override):
        config_override({
            'sources': {'TEST': {'authoritative': True}},
            'rpki': {'notification_invalid_enabled': True},
        })
        mock_dh = Mock(spec=DatabaseHandler)
        mock_dq = Mock(spec=RPSLDatabaseQuery)
        monkeypatch.setattr('irrd.rpki.notifications.RPSLDatabaseQuery', lambda columns: mock_dq)
        mock_email = Mock(spec=send_email)
        monkeypatch.setattr('irrd.rpki.notifications.send_email', mock_email)

        rpsl_dicts_now_invalid = [
            {'source': 'TEST', 'object_text': SAMPLE_ROUTE + 'mnt-by: DOESNOTEXIST-MNT\n', 'rpki_status': RPKIStatus.invalid},
            {'source': 'TEST', 'object_text': SAMPLE_ROUTE6, 'rpki_status': RPKIStatus.valid},  # should be ignored
            {'source': 'TEST2', 'object_text': SAMPLE_ROUTE6, 'rpki_status': RPKIStatus.invalid},  # should be ignored
        ]

        query_results = iter([
            [
                {'rpsl_pk': 'TEST-MNT', 'parsed_data': {'tech-c': ['PERSON-TEST', 'DOESNOTEXIST-TEST']}},
            ],
            [
                {'rpsl_pk': 'PERSON-TEST', 'parsed_data': {'e-mail': ['person@xample.com', 'person2@example.com']}},
                {'rpsl_pk': 'IGNORED-TEST', 'parsed_data': {'e-mail': ['ignored@xample.com']}},
            ],
        ])
        mock_dh.execute_query = lambda q: next(query_results)
        notified = notify_rpki_invalid_owners(mock_dh, rpsl_dicts_now_invalid)
        assert notified == 2

        assert flatten_mock_calls(mock_dq) == [
            ['sources', (['TEST'],), {}],
            ['rpsl_pks', ({'TEST-MNT', 'DOESNOTEXIST-MNT'},), {}],
            ['object_classes', (['mntner'],), {}],
            ['sources', (['TEST'],), {}],
            ['rpsl_pks', ({'PERSON-TEST', 'DOESNOTEXIST-TEST'},), {}],
            ['object_classes', (['role', 'person'],), {}]]

        assert len(mock_email.mock_calls) == 2
        actual_recipients = {mock_email.mock_calls[0][1][0], mock_email.mock_calls[1][1][0]}
        expected_recipients = {'person@xample.com', 'person2@example.com'}
        assert actual_recipients == expected_recipients
        assert mock_email.mock_calls[0][1][1] == 'route(6) objects in TEST marked RPKI invalid'
        assert mock_email.mock_calls[0][1][2] == textwrap.dedent("""
            This is to notify that 1 route(6) objects for which you are a
            contact have been marked as RPKI invalid. This concerns
            objects in the TEST database.
            
            You have received this message because your e-mail address is
            listed in one or more of the tech-c or admin-c contacts, on
            the maintainer(s) for these route objects.
            
            The 1 route(6) objects listed below have been validated using
            RPKI origin validation, and found to be invalid. This means that
            these objects are no longer visible on the IRRd instance that
            sent this e-mail.
            
            This may affect routing filters based on queries to this IRRd
            instance. It is also no longer possible to modify these objects.
            
            To resolve this situation, create or modify ROA objects that
            result in these route(6) being valid, or not_found. If this
            happens, the route(6) objects will return to being visible.
            You may also delete these objects if they are no longer
            relevant.
            
            The following objects are affected:
            ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            
            route:          192.0.2.0/24
            descr:          example route
            descr:          the route attribute should have the extra zero removed,
            +               but this value should not: 192.0.02.0/24
            origin:         AS65537
            member-of:      RS-TEST
            mnt-by:         TEST-MNT
            changed:        changed@example.com 20190701 # comment
            source:         TEST
            remarks:        remark
            mnt-by:         DOESNOTEXIST-MNT
            
            ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        """).strip()

    def test_notify_disabled(self, monkeypatch, config_override):
        config_override({
            'sources': {'TEST': {'authoritative': True}},
            'rpki': {'notification_invalid_enabled': False},
        })
        mock_dh = Mock(spec=DatabaseHandler)
        mock_email = Mock()
        monkeypatch.setattr('irrd.rpki.notifications.send_email', mock_email)

        rpsl_dicts_now_invalid = [
            {'source': 'TEST', 'object_text': SAMPLE_ROUTE6, 'rpki_status': RPKIStatus.invalid},
        ]

        notified = notify_rpki_invalid_owners(mock_dh, rpsl_dicts_now_invalid)
        assert notified == 0
        assert len(mock_email.mock_calls) == 0

    def test_notify_no_relevant_objects(self, monkeypatch, config_override):
        config_override({
            'sources': {'TEST': {'authoritative': True}},
            'rpki': {'notification_invalid_enabled': True},
        })
        mock_dh = Mock(spec=DatabaseHandler)
        mock_email = Mock()
        monkeypatch.setattr('irrd.rpki.notifications.send_email', mock_email)

        rpsl_dicts_now_invalid = [
            # should be ignored
            {'source': 'TEST2', 'object_text': SAMPLE_ROUTE6, 'rpki_status': RPKIStatus.invalid},
        ]

        notified = notify_rpki_invalid_owners(mock_dh, rpsl_dicts_now_invalid)
        assert notified == 0
        assert len(mock_email.mock_calls) == 0