import mock
import yaml
from django.test import TestCase, LiveServerTestCase, Client

from budgetportal.models import InfrastructureProject, MAPIT_POINT_API_URL, CKAN_DATASTORE_URL
import json
from mock import Mock

# Hacky make sure we don't call out to openspending.
import requests

requests.get = Mock
requests.Session = Mock


with open('budgetportal/tests/test_data/test_infrastructure_projects.json', 'r') as mock_data:
    MOCK_DATA = json.load(mock_data)


class ProjectedExpenditureTestCase(TestCase):
    """ Unit tests for get_projected_expenditure function """

    def setUp(self):
        self.fake_valid_records = [
            {'Budget Phase': 'test phase one', 'Amount': 100},
            {'Budget Phase': 'test phase one', 'Amount': 100},
            {'Budget Phase': 'test phase two', 'Amount': 100},
            {'Budget Phase': 'MTEF', 'Amount': 200},
            {'Budget Phase': 'MTEF', 'Amount': 200},
            {'Budget Phase': 'MTEF', 'Amount': 200},
        ]

    def test_success(self):
        projected_expenditure = InfrastructureProject._calculate_projected_expenditure(
            self.fake_valid_records
        )
        self.assertEqual(projected_expenditure, 600)

    def test_empty_records_returns_zero(self):
        projected_expenditure = InfrastructureProject._calculate_projected_expenditure([])
        self.assertEqual(projected_expenditure, 0)

    def test_string_raises_type_error(self):
        self.assertRaises(
            TypeError,
            InfrastructureProject._calculate_projected_expenditure,
            'test string raises exception'
        )


class CoordinatesTestCase(TestCase):
    """ Unit tests for parsing coordinates """

    def test_success_simple_format(self):
        raw_coord_string = '-26.378582,27.654933'
        cleaned_coord_object = InfrastructureProject._parse_coordinate(
            raw_coord_string
        )
        self.assertEqual(
            cleaned_coord_object,
            {
                'latitude': -26.378582,
                'longitude': 27.654933
            }
        )

    def test_failure_int_raises_type_error(self):
        invalid_coordinate = 25
        self.assertRaises(
            TypeError,
            InfrastructureProject._parse_coordinate,
            invalid_coordinate
        )

    def test_failure_list_raises_type_error(self):
        invalid_coordinate = [25, 23]
        self.assertRaises(
            TypeError,
            InfrastructureProject._parse_coordinate,
            invalid_coordinate
        )

    def test_success_multiple_coordinates(self):
        raw_coordinate_string = '-26.378582,27.654933 and -22.111222,23.333444'
        coords = InfrastructureProject._clean_coordinates(raw_coordinate_string)
        self.assertIn(
            {
                'latitude': -26.378582,
                'longitude': 27.654933
            },
            coords
        )
        self.assertIn(
            {
                'latitude': -22.111222,
                'longitude': 23.333444
            },
            coords
        )

    def test_empty_response_for_invalid_value(self):
        raw_coordinate_string = 'test string with, no coords and'
        coords = InfrastructureProject._clean_coordinates(raw_coordinate_string)
        self.assertEqual(coords, [])


class ExpenditureTestCase(TestCase):
    """ Unit tests for expenditure functions """

    def setUp(self):
        self.fake_valid_records = [
            {
                'Financial Year': 2030,
                'Budget Phase': 'fake budget phase',
                'Amount': 123
            },
            {
                'Financial Year': 2031,
                'Budget Phase': 'fake budget phase 2',
                'Amount': 1000
            },
        ]
        self.expected_output_2030 = {
            'year': 2030,
            'amount': 123.0,
            'budget_phase': 'fake budget phase'
        }
        self.expected_output_2031 = {
            'year': 2031,
            'amount': 1000,
            'budget_phase': 'fake budget phase 2'
        }

    def test_success_build_expenditure_item(self):
        expenditure_item = InfrastructureProject._build_expenditure_item(self.fake_valid_records[0])
        self.assertEqual(
            expenditure_item,
            self.expected_output_2030
        )

    def test_failure_missing_fields(self):
        self.assertRaises(
            KeyError,
            InfrastructureProject._build_expenditure_item,
            {
                'Not enough keys': 'to parse successfully'
            }
        )

    def test_success_build_complete_expenditure(self):
        complete_expenditure = InfrastructureProject._build_complete_expenditure(self.fake_valid_records)
        self.assertIn(
            self.expected_output_2030,
            complete_expenditure
        )
        self.assertIn(
            self.expected_output_2031,
            complete_expenditure
        )


class MockResponse:
    def __init__(self, json_data, status_code):
        self.json_data = json_data
        self.status_code = status_code

    def json(self):
        return self.json_data

    def raise_for_status(self):
        return None


# This method will be used by the mock to replace requests.get
def mocked_requests_get(*args, **kwargs):

    if args[0] == MAPIT_POINT_API_URL.format(25.312526, -27.515232):
        return MockResponse(
            {4288: {'name': 'Fake Province 1'}},
            200
        )
    elif args[0] == MAPIT_POINT_API_URL.format(24.312526, -26.515232):
        return MockResponse(
            {},
            200
        )
    elif args[0] == CKAN_DATASTORE_URL and 'health-standard-fake-project' in kwargs['params']['sql']:
        return MockResponse(
            {
                'result': {
                    'records': MOCK_DATA['detail_records']
                }
            },
            200
        )
    elif args[0] == CKAN_DATASTORE_URL:
        return MockResponse(
            {
                'result': {
                    'records': MOCK_DATA['overview_records']
                }
            },
            200
        )
    elif args[0] == MAPIT_POINT_API_URL.format(29.45397, -31.45019):
        return MockResponse(
            {4288: {'name': 'Fake Province 3'}},
            200
        )
    elif args[0] == MAPIT_POINT_API_URL.format(25.443304, -33.399790):
        return MockResponse(
            {4288: {'name': 'Fake Province 4'}},
            200
        )
    elif args[0] == MAPIT_POINT_API_URL.format(15.443304, -30.399790):
        return MockResponse(
            {4288: {'name': 'Fake Province 5'}},
            200
        )
    return MockResponse(None, 404)


class ProvinceTestCase(TestCase):

    def setUp(self):
        self.test_coordinates_one = {
            'longitude': 25.312526,
            'latitude': -27.515232
        }
        self.test_coordinates_two = {
            'longitude': 24.312526,
            'latitude': -26.515232
        }

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_success_one_result(self, mock_get):
        province = InfrastructureProject._get_province_from_coord(self.test_coordinates_one)
        self.assertEqual(province, 'Fake Province 1')

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_success_no_results(self, mock_get):
        province = InfrastructureProject._get_province_from_coord(self.test_coordinates_two)
        self.assertEqual(province, None)

    def test_success_province_from_name(self):
        province = InfrastructureProject._get_province_from_project_name('Eastern Cape: A New Test')
        self.assertEqual(province, 'Eastern Cape')


class MockDataset(mock.Mock):
    def get_resource(self, format):
        return {'id': 'fake id'}

    def get_url_path(self):
        return 'fake path'


empty_ckan_response = MockResponse(
            {
                'result': {
                    'records': []
                }
            },
            200
        )


class OverviewIntegrationTest(LiveServerTestCase):

    def setUp(self):
        self.expected_expenditure = [
            {'amount': 100.0, 'budget_phase': 'fake old phase', 'year': '2045'},
            {'amount': 100.0, 'budget_phase': 'fake old phase', 'year': '2046'},
            {'amount': 100.0, 'budget_phase': 'fake old phase', 'year': '2047'},
            {'amount': 100.0, 'budget_phase': 'fake current phase', 'year': '2048'},
            {'amount': 100.0, 'budget_phase': 'MTEF', 'year': '2049'},
            {'amount': 100.0, 'budget_phase': 'MTEF', 'year': '2050'},
            {'amount': 100.0, 'budget_phase': 'MTEF', 'year': '2051'}
        ]

    @mock.patch('budgetportal.models.InfrastructureProject.get_dataset', return_value=None)
    def test_missing_dataset_returns_404(self, mock_dataset):
        c = Client()
        response = c.get('/infrastructure-projects.yaml')
        self.assertEqual(response.status_code, 404)

    @mock.patch('budgetportal.models.InfrastructureProject.get_dataset', return_value=MockDataset())
    @mock.patch('requests.get', return_value=empty_ckan_response)
    def test_success_empty_projects(self, mock_dataset, mock_get):
        """ Test that it exists and that the correct years are linked. """
        c = Client()
        response = c.get('/infrastructure-projects.yaml')
        content = yaml.load(response.content)
        self.assertEqual(content['projects'], [])
        self.assertEqual(content['dataset_url'], 'fake path')
        self.assertEqual(content['description'], 'Infrastructure projects in South Africa for 2019-20')
        self.assertEqual(content['selected_tab'], 'infrastructure-projects')
        self.assertEqual(content['slug'], 'infrastructure-projects')
        self.assertEqual(content['title'], 'Infrastructure Projects - vulekamali')

    @mock.patch('budgetportal.models.InfrastructureProject.get_dataset', return_value=MockDataset())
    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_success_with_projects(self, mock_dataset, mock_get):
        """ Test that it exists and that the correct years are linked. """
        c = Client()
        response = c.get('/infrastructure-projects.yaml')
        content = yaml.load(response.content)
        self.assertEqual(len(content['projects']), 2)

        # First project (single coords, province)
        first_test_project = filter(lambda x: x['name'] == 'Standard fake project', content['projects'])[0]
        self.assertEqual(first_test_project['dataset_url'], 'fake path')
        self.assertEqual(first_test_project['description'], 'Typical project description')
        self.assertEqual(first_test_project['detail'], '/infrastructure-projects/health-standard-fake-project')
        self.assertEqual(first_test_project['infrastructure_type'], 'fake type')
        self.assertIn({'latitude': -31.45019, 'longitude': 29.45397}, first_test_project['coordinates'])
        self.assertEqual(len(first_test_project['coordinates']), 1)
        self.assertEqual(len(first_test_project['expenditure']), 7)
        for item in self.expected_expenditure:
            self.assertIn(item, first_test_project['expenditure'])
        self.assertEqual(first_test_project['nature_of_investment'], 'standard fake investment')
        self.assertEqual(first_test_project['page_title'], 'Standard fake project - vulekamali')
        self.assertEqual(first_test_project['projected_budget'], 300.0)
        self.assertIn('Fake Province 3', first_test_project['provinces'])
        self.assertEqual(len(first_test_project['provinces']), 1)
        self.assertEqual(first_test_project['slug'], '/infrastructure-projects/health-standard-fake-project')
        self.assertEqual(first_test_project['stage'], 'Design')
        self.assertEqual(first_test_project['total_budget'], 100.0)

        # Second project (multiple coords, provinces)
        second_test_project = filter(lambda x: x['name'] == 'another fake project', content['projects'])[0]
        self.assertIn({'latitude': -33.399790, 'longitude': 25.443304}, second_test_project['coordinates'])
        self.assertIn({'latitude': -30.399790, 'longitude': 15.443304}, second_test_project['coordinates'])
        self.assertEqual(len(second_test_project['coordinates']), 2)
        self.assertIn('Fake Province 4', second_test_project['provinces'])
        self.assertIn('Fake Province 5', second_test_project['provinces'])
        self.assertEqual(len(second_test_project['provinces']), 2)


class DetailIntegrationTest(LiveServerTestCase):

    def setUp(self):
        self.expected_expenditure = [
            {'amount': 100.0, 'budget_phase': 'fake old phase', 'year': '2045'},
            {'amount': 100.0, 'budget_phase': 'fake old phase', 'year': '2046'},
            {'amount': 100.0, 'budget_phase': 'fake old phase', 'year': '2047'},
            {'amount': 100.0, 'budget_phase': 'fake current phase', 'year': '2048'},
            {'amount': 100.0, 'budget_phase': 'MTEF', 'year': '2049'},
            {'amount': 100.0, 'budget_phase': 'MTEF', 'year': '2050'},
            {'amount': 100.0, 'budget_phase': 'MTEF', 'year': '2051'}
        ]
        self.project_slug = 'standard-fake-project'
        self.department_slug = 'health'

    @mock.patch('budgetportal.models.InfrastructureProject.get_dataset', return_value=None)
    def test_missing_dataset_returns_404(self, mock_dataset):
        c = Client()
        response = c.get('/infrastructure-projects/{}-{}.yaml'.format(self.department_slug, self.project_slug))
        self.assertEqual(response.status_code, 404)

    @mock.patch('budgetportal.models.InfrastructureProject.get_dataset', return_value=MockDataset())
    @mock.patch('requests.get', return_value=empty_ckan_response)
    def test_empty_project_records_returns_404(self, mock_dataset, mock_get):
        """ Test that it exists and that the correct years are linked. """
        c = Client()
        response = c.get('/infrastructure-projects/{}-{}.yaml'.format(self.department_slug, self.project_slug))
        self.assertEqual(response.status_code, 404)

    @mock.patch('budgetportal.models.InfrastructureProject.get_dataset', return_value=MockDataset())
    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_success_with_projects(self, mock_dataset, mock_get):
        """ Test that it exists and that the correct years are linked. """
        c = Client()
        response = c.get('/infrastructure-projects/{}-{}.yaml'.format(self.department_slug, self.project_slug))
        content = yaml.load(response.content)

        self.assertEqual(content['dataset_url'], 'fake path')
        self.assertEqual(content['description'], 'Typical project description')
        self.assertEqual(content['infrastructure_type'], 'fake type')
        self.assertIn({'latitude': -31.45019, 'longitude': 29.45397}, content['coordinates'])
        self.assertEqual(len(content['coordinates']), 1)
        self.assertEqual(len(content['expenditure']), 7)
        for item in self.expected_expenditure:
            self.assertIn(item, content['expenditure'])
        self.assertEqual(content['nature_of_investment'], 'standard fake investment')
        self.assertEqual(content['title'], 'Standard fake project - vulekamali')
        self.assertEqual(content['projected_budget'], 300.0)
        self.assertIn('Fake Province 3', content['provinces'])
        self.assertEqual(len(content['provinces']), 1)
        self.assertEqual(content['slug'], '/infrastructure-projects/health-standard-fake-project')
        self.assertEqual(content['stage'], 'Design')
        self.assertEqual(content['total_budget'], 100.0)
