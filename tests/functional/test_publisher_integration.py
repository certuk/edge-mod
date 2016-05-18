import os
import subprocess

import repository.test as edge_test
from adapters.certuk_mod.publisher.publisher_edge_object import PublisherEdgeObject

os.environ['DJANGO_SETTINGS_MODULE'] = 'repository.settings'


class PublisherIntegrationTests(edge_test.TestCase):

    fixtures = ['stix', 'user']

    def loaddata(self, labels):
        for label in labels:
            pathname = os.path.dirname(__file__) + '/fixtures/' + label + '.json'
            subprocess.Popen(['mongoimport', '-d', edge_test.TEST_DB_NAME, '-c', label, '--file', pathname],
                             stdout=subprocess.PIPE).communicate()

    def test_PublisherEdgeObject_RootHasGrandChildrenFromDifferentNamespace_NamespacePresent(self):
        edge_object = PublisherEdgeObject.load('PurpleSecureSystems:indicator-02db75d2-77e2-4774-a219-293318051515')
        namespaces = edge_object.ns_dict()
        self.assertEqual(namespaces, {
            'http://www.purplesecure.com': 'PurpleSecureSystems',
            'http://www.fireeye.com': 'fireeye'
        })

    def test_PublisherEdgeObject_CreatedByUserNamePresent(self):
        edge_object = PublisherEdgeObject.load('PurpleSecureSystems:indicator-02db75d2-77e2-4774-a219-293318051515')
        username = edge_object.created_by_username
        self.assertEqual(username, 'admin')

