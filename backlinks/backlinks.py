import os
from django.conf import settings
from mongoengine.connection import get_db
from edge.tools import StopWatch
from adapters.certuk_mod.common.activity import save as log_activity
from datetime import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'repository.settings')
if not hasattr(settings, 'BASE_DIR'): raise Exception('could not load settings.py')


class STIXBacklinks(object):
    PAGE_SIZE = 5000

    def __init__(self):
        pass

    def run(self):
        def _process_bulk_op():
            bulk_op = db.stix_backlinks.initialize_unordered_bulk_op()
            for blo in dict_bls.keys():
                c = db.stix_backlinks.find_one({'_id': blo})
                existing_bls = {}
                if c:
                    existing_bls = c['value']

                for new_bl in dict_bls[blo]:
                    existing_bls[new_bl['id']] = new_bl['type']

                bulk_op.find({'_id': blo}).upsert().update({"$set": {'value': existing_bls}})
            try:
                bulk_op.execute()
            except Exception:
                pass

        db = get_db()
        db.stix_backlinks.drop()
        db.stix_backlinks.update({"_id": "max_created_on"}, {'value': datetime.now()}, True)

        update_timer = StopWatch()

        dict_bls = {}
        for doc in db.stix.find({}):

            if 'data' in doc and 'edges' in doc['data']:
                for edge in doc['data']['edges'].keys():
                    dict_bls.setdefault(edge, []).append({"id": doc['_id'], "type": doc['type']})

            if not (len(dict_bls) % STIXBacklinks.PAGE_SIZE):
                _process_bulk_op()
                dict_bls = {}

        if len(dict_bls):
            _process_bulk_op()

        log_activity("system", 'Backlink', 'INFO',
                     "%s : Updated for %d objects in %ds" %
                     (
                         'Full Rebuild',
                         db.stix.count(),
                         update_timer.sec())
                     )


if __name__ == '__main__':
    STIXBacklinks().run()