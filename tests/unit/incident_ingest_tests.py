import mock
import unittest

from adapters.certuk_mod.ingest.views import create_time, create_reporter, \
    create_intended_effects, status_checker, initialise_draft


class IncidentIngestTests(unittest.TestCase):
    def setUp(self):
        self.draft = {
            'attributed_actors': [],
            'categories': [''],
            'description': '',
            'discovery_methods': [],
            'effects': [],
            'external_ids': [{'source': '', 'id': '14007indicator536.csv'}],
            'id': 'pss:inc-00000001-0001-0001-0001-00000001',
            'id_ns': 'http://www.purplesecure.com',
            'intended_effects': [''],
            'leveraged_ttps': [],
            'related_incidents': [],
            'related_indicators': [],
            'related_observables': [],
            'reporter': {'name': 'Purple', 'specification': {'organisation_info': {'industry_type': ''}}},
            'responders': [],
            'short_description': '',
            'status': 'Closed',
            'title': 'RTIR 1500',
            'tlp': '',
            'trustgroups': [],
            'victims': [{'name': '', 'specification': {'organisation_info': {'industry_type': 'Water'}}}],
            'stixtype': 'inc',
            'time': {}
        }

    def test_no_time(self):
        data = {'Created': '',
                'CustomField.{Containment Achieved}': '',
                'CustomField.{First Data Exfiltration}': '',
                'CustomField.{First Malicious Action}': '',
                'CustomField.{Incident Discovery}': '',
                'CustomField.{Incident Reported}': '',
                'CustomField.{Initial Compromise}': '',
                'CustomField.{Restoration Achieved}': '',
                'Resolved': ''}
        time = create_time(data)
        self.assertEqual(time, {})

    def test_with_time(self):
        data = {'Created': '',
                'CustomField.{Containment Achieved}': 'Sun Oct 05 00:00:00 2014',
                'CustomField.{First Data Exfiltration}': 'Wed Oct 01 00:00:00 2014',
                'CustomField.{First Malicious Action}': 'Tue Sep 30 00:00:00 2014',
                'CustomField.{Incident Discovery}': '',
                'CustomField.{Incident Reported}': '',
                'CustomField.{Initial Compromise}': '',
                'CustomField.{Restoration Achieved}': '',
                'Resolved': ''}
        time = create_time(data)
        compare_time = {'containment_achieved': {'precision': 'second',
                                                 'value': '2014-10-05T00:00:00'},
                        'first_data_exfiltration': {'precision': 'second',
                                                    'value': '2014-10-01T00:00:00'},
                        'first_malicious_action': {'precision': 'second',
                                                   'value': '2014-09-30T00:00:00'}}
        self.assertDictEqual(time, compare_time)

    def test_intended_effects(self):
        data = {'CustomField.{Intended Effect}': 'Fraud<br />Brand Damage<br />Advantage - Economic'}
        intended_effects = create_intended_effects(data)
        compare_effects = ['Fraud', 'Brand Damage', 'Advantage - Economic']
        self.assertListEqual(intended_effects, compare_effects)

    def test_no_effects(self):
        data = {'CustomField.{Intended Effect}': ''}
        intended_effects = create_intended_effects(data)
        compare_effects = ['']
        self.assertListEqual(intended_effects, compare_effects)

    def test_no_status(self):
        data = {'Status': ''}
        status = status_checker(data)
        compare_status = ''
        self.assertEquals(status, compare_status)

    def test_status_resolved(self):
        data = {'Status': 'resolved'}
        status = status_checker(data)
        compare_status = 'Closed'
        self.assertEquals(status, compare_status)

    def test_status_not_resolved(self):
        data = {'Status': 'New'}
        status = status_checker(data)
        compare_status = 'New'
        self.assertEquals(status, compare_status)

    def test_reporter_type(self):
        data = {'CustomField.{Reporter Type}': 'Domestic Source<br />Government Agency'}
        reporter = create_reporter(data)
        compare_reporter = 'Domestic Source, Government Agency'
        self.assertEquals(reporter, compare_reporter)

    @mock.patch('adapters.certuk_mod.ingest.views.IDManager')
    @mock.patch('adapters.certuk_mod.ingest.views.create_time')
    @mock.patch('adapters.certuk_mod.ingest.views.create_reporter')
    @mock.patch('adapters.certuk_mod.ingest.views.create_intended_effects')
    @mock.patch('adapters.certuk_mod.ingest.views.status_checker')
    def test_initialise_draft(self, mock_status, mock_intended_effects, mock_reporter, mock_time, mock_manager):
        mock_status.return_value = 'Closed'
        mock_intended_effects.return_value = ['']
        mock_reporter.return_value = 'Purple'
        mock_time.return_value = {}
        mock_manager().get_namespace.return_value = 'http://www.purplesecure.com'
        mock_manager().get_new_id.return_value = 'pss:inc-00000001-0001-0001-0001-00000001'
        data = {
            'id': '1500',
            'CustomField.{Indicator Data Files}': '14007indicator536.csv',
            'Created': '',
            'CustomField.{Containment Achieved}': '',
            'CustomField.{First Data Exfiltration}': '',
            'CustomField.{First Malicious Action}': '',
            'CustomField.{Incident Discovery}': '',
            'CustomField.{Incident Reported}': '',
            'CustomField.{Initial Compromise}': '',
            'CustomField.{Restoration Achieved}': '',
            'CustomField.{Description}': '',
            'CustomField.{Category}': '',
            'CustomField.{Reporter Type}': '',
            'CustomField.{Incident Sector}': 'Water',
            'Status': '',
            'CustomField.{Intended Effect}': '',
            'Resolved': ''
        }
        draft = initialise_draft(data)
        mock_status.assert_called_with(data)
        mock_intended_effects.assert_called_with(data)
        mock_reporter.assert_called_with(data)
        mock_time.assert_called_with(data)
        self.assertDictEqual(draft, self.draft)