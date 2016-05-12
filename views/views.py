import os
import urllib2
import json
import datetime
from dateutil import tz
import mimetypes

from django.http import FileResponse, HttpResponseNotFound
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.conf import settings

from users.decorators import superuser_or_staff_role, json_body
from users.models import Draft
from edge.generic import EdgeObject
from edge import IDManager

from adapters.certuk_mod.publisher.package_publisher import Publisher
from adapters.certuk_mod.publisher.publisher_config import PublisherConfig
from adapters.certuk_mod.publisher.package_generator import PackageGenerator
from adapters.certuk_mod.publisher.publisher_edge_object import PublisherEdgeObject
from adapters.certuk_mod.validation.package.validator import PackageValidationInfo
from adapters.certuk_mod.validation.builder.validator import BuilderValidationInfo
from adapters.certuk_mod.common.views import error_with_message

import adapters.certuk_mod.builder.customizations as cert_builder

from adapters.certuk_mod.builder.kill_chain_definition import KILL_CHAIN_PHASES
from adapters.certuk_mod.common.views import activity_log, ajax_activity_log
from adapters.certuk_mod.extract.views import extract_upload, extract_visualiser, extract_visualiser_get, \
    extract_visualiser_item_get, extract, extract_visualiser_merge_observables, extract_visualiser_delete_observables
from adapters.certuk_mod.common.logger import log_error, get_exception_stack_variable
from adapters.certuk_mod.cron import setup as cron_setup

from adapters.certuk_mod.cron.views import ajax_get_purge_task_status, ajax_run_purge
from adapters.certuk_mod.retention.views import ajax_get_retention_config, ajax_reset_retention_config, \
    ajax_set_retention_config

from adapters.certuk_mod.cron.views import ajax_get_fts_task_status, ajax_run_fts
from adapters.certuk_mod.fts.views import ajax_get_fts_config, ajax_reset_fts_config, \
    ajax_set_fts_config

from adapters.certuk_mod.dedup.views import duplicates_finder, ajax_load_duplicates, ajax_load_object, \
    ajax_load_parent_ids, ajax_import
from adapters.certuk_mod.config.views import ajax_get_crm_url, ajax_set_crm_url, ajax_get_cert_config
from adapters.certuk_mod.audit import setup as audit_setup, status
from adapters.certuk_mod.audit.event import Event
from adapters.certuk_mod.audit.handlers import log_activity
from adapters.certuk_mod.audit.message import format_audit_message

from adapters.certuk_mod.common.objectid import discover as objectid_discover, find_id as objectid_find

from adapters.certuk_mod.retention.purge import STIXPurge

from adapters.certuk_mod.validation import FieldValidationInfo, ValidationStatus
from adapters.certuk_mod.visualiser.views import visualiser_discover, visualiser_not_found, visualiser_view, \
    visualiser_get, \
    visualiser_item_get
from users.models import Repository_User

from adapters.certuk_mod.timeline.views import ajax_incident_timeline, timeline_discover, incident_timeline

audit_setup.configure_publisher_actions()
cert_builder.apply_customizations()
cron_setup.create_jobs()
mimetypes.init()
MAGIC_QUERY_LIMIT = 20000

@login_required
def static(request, path):
    clean_path = urllib2.unquote(path)
    if "../" not in clean_path:
        content_type, _ = mimetypes.guess_type(clean_path)
        return FileResponse(
                open(os.path.dirname(__file__) + "/../static/" + clean_path, mode="rb"),
                content_type=content_type
        )
    else:
        return HttpResponseNotFound()


@login_required
def discover(request):
    return objectid_discover(request, "publisher_review", "publisher_not_found")


TYPE_TO_URL = {
    'cam': 'campaign',
    'coa': 'course_of_action',
    'tgt': 'exploit_target',
    'inc': 'incident',
    'ind': 'indicator',
    'obs': 'observable',
    'act': 'threat_actor',
    'ttp': 'ttp'
}

@login_required
def clone(request):
    stix_id = objectid_find(request)
    try:
        if stix_id:
            edge_object = EdgeObject.load(stix_id)
            if edge_object.ty == 'obs':
                return error_with_message(request, "Observables cannot be cloned")
            new_id = IDManager().get_new_id(edge_object.ty)
            draft = edge_object.to_draft()
            draft['id'] = new_id
            Draft.upsert(edge_object.ty, draft, request.user)
            return redirect('/' + TYPE_TO_URL[edge_object.ty] + '/build/' + new_id, request)
        else:
            return error_with_message(request,
                                "No clonable object found; please only choose the clone option from an object's summary or external publish page")
    except Exception as e:
        ext_ref_error = "not found"
        if e.message.endswith(ext_ref_error):
            return error_with_message(request,
                                "Unable to load object as some external references were not found: " + e.message[0:-len(
                                        ext_ref_error)])
        else:
            return error_with_message(request, e.message)


def _get_request_username(request):
    if hasattr(request, "user") and hasattr(request.user, "username"):
        return request.user.username
    return ""


@login_required
def review(request, id_):
    root_edge_object = PublisherEdgeObject.load(id_)
    package = PackageGenerator.build_package(root_edge_object)
    validation_info = PackageValidationInfo.validate(package)

    req_user = _get_request_username(request)
    if root_edge_object.created_by_username != req_user:
        validation_info.validation_dict.update({id_: {"created_by":
                                                          {"status": ValidationStatus.WARN,
                                                           "message": "This object was created by %s not %s"
                                                                      % (root_edge_object.created_by_username,
                                                                         req_user)}}})

    request.breadcrumbs([("Publisher", "")])
    return render(request, "publisher_review.html", {
        "root_id": id_,
        "package": package,
        "validation_info": validation_info,
        "kill_chain_phases": {item['phase_id']: item['name'] for item in KILL_CHAIN_PHASES}
    })


@login_required
def not_found(request):
    return render(request, "publisher_not_found.html", {})


@login_required
@superuser_or_staff_role
def config(request):
    request.breadcrumbs([("CERT-UK Configuration", "")])
    return render(request, "config.html", {})


@login_required
@superuser_or_staff_role
@json_body
def ajax_get_sites(request, data):
    # The generic settings pages could define callbacks for dropdown options.
    # Probably just provide this data at the Django template rendering stage instead.
    # Or maybe make AJAX call optional, e.g. for large option lists?
    success = True
    error_message = ""
    sites = []

    try:
        sites = PublisherConfig.get_sites()
    except Exception, e:
        success = False
        error_message = e.message

    return {
        'success': success,
        'error_message': error_message,
        'sites': sites
    }


@login_required
@json_body
def ajax_get_datetime(request, data):
    configuration = settings.ACTIVE_CONFIG
    current_date_time = datetime.datetime.now(tz.gettz(configuration.by_key('display_timezone'))).strftime(
            '%Y-%m-%dT%H:%M:%S')
    return {'result': current_date_time}


@login_required
@superuser_or_staff_role
@json_body
def ajax_set_publish_site(request, data):
    success = True
    error_message = ''
    site_id = data.get('site_id', '')

    try:
        PublisherConfig.update_config(site_id)
    except Exception, e:
        success = False
        error_message = e.message
        site_id = ''

    return {
        'success': success,
        'saved_id': site_id,
        'error_message': error_message
    }


OnPublish = Event()
OnPublish.set_handler("Write to log", log_activity)


@login_required
@json_body
def ajax_publish(request, data):
    success = True
    error_message = ""
    root_id = None

    try:
        root_id = data['root_id']
        edge_object = PublisherEdgeObject.load(root_id)
        package = PackageGenerator.build_package(edge_object)
        namespace_info = edge_object.ns_dict()
        Publisher.push_package(package, namespace_info)
    # Narrow down which exceptions we catch...?
    except Exception, e:
        message = ''
        taxii_response = get_exception_stack_variable('tr')
        if taxii_response:
            message = '\nTAXII Staus Message:\n' + json.dumps(taxii_response.to_dict())
        log_error(e, 'Publisher', message)

        success = False
        error_message = e.message

    OnPublish.raise_event(ajax_publish, publish_status=status.PUBLISH_SUCCESS if success else status.PUBLISH_FAIL,
                          stix_id=root_id, user=request.user,
                          message=format_audit_message(error_message, data.get('publicationMessage')))

    # The whole try/except... return { success.. } thing seems repeated quite a bit for
    # our ajax handlers (and also in the core code)...
    return {
        'success': success,
        'error_message': error_message
    }


@login_required
@json_body
def ajax_validate(request, data):
    validation_info = {}
    success = True
    error_message = ''

    try:
        validation_info = BuilderValidationInfo.validate(data).validation_dict
    except Exception, e:
        success = False
        error_message = e.message

    return {
        'success': success,
        'error_message': error_message,
        'validation_info': validation_info
    }

@json_body
@login_required
def ajax_load_catalog(request, d):
    req_size = int(d.pop('size', 0))
    req_type = d.pop('type', '').strip()
    req_offset = int(d.pop('offset', 0))
    req_search = d.pop('search', '').strip()
    req_datefilter = d.pop('datefilter', '')
    req_order = d.pop('order', True)
    req_show_all = d.pop('showAll', False)
    if d: raise Exception("json request included unknown items")

    def magic_gather_and_sort(criteria, offset, size):

        def only_unique_by_hash(cursor):
            hashes = set()
            counter = 0
            for doc in cursor:
                counter += 1
                if doc['data']['hash'] in hashes: continue
                hashes.add(doc['data']['hash'])
                yield counter, doc

        required = {'_id': 1, 'created_on': 1, 'data.hash': 1}
        cursor = get_db().stix.find(criteria, required, skip=0, limit=MAGIC_QUERY_LIMIT)

        data = []
        scan_count = 0
        unique_count = 0
        for scan_count, doc in only_unique_by_hash(cursor):
            unique_count += 1
            if len(data) < 1000 + offset:
                data.append({'created_on': doc['created_on'], '_id': doc['_id']})
            else:
                data = sorted(data, key=lambda item: item['created_on'], reverse=req_order)
                del data[offset + size : len(data)]

        data = sorted(data, key=lambda item: item['created_on'], reverse=req_order)
        del data[0 : offset]
        del data[size : len(data)]
        return data, unique_count, scan_count

    total_count = get_db().stix.find().count()

    if total_count > MAGIC_QUERY_LIMIT and (not req_type) and (not req_search):
        # No criteria and a LOT of data in the database
        no_criteria = True
        count = total_count
        unreliable_sort = True
        results = []
    else:
        no_criteria = False
        query = {'txn': None}
        if not req_show_all:
            query.update(filter_namespace())
        query.update(filter_date(req_datefilter))
        query.update(filter_type(req_type))
        query.update(filter_keywords(req_search))
        query.update(filter_out_composite_observables())
        query.update(filter_out_envelopes())
        query.update(request.user.filters())

        data, unique_count, scan_count = magic_gather_and_sort(query, req_offset, req_size)
        count = unique_count
        unreliable_sort = scan_count >= MAGIC_QUERY_LIMIT
        results = (doc['_id'] for doc in data)

    loaded = (load_object_for_catalog(idref) for idref in results)
    return {
        'data': [object_to_js_for_catalog(doc) for doc in loaded],
        'no_criteria': no_criteria,
        'unreliable_sort': unreliable_sort,
        'count': count,
        'success': True,
    }

from catalog.views import filter_date, filter_type, filter_keywords, filter_out_composite_observables, filter_out_envelopes, object_to_js_for_catalog, load_object_for_catalog
from mongoengine.connection import get_db

def filter_namespace():
    return {'data.idns': LOCAL_NAMESPACE}

from edge import LOCAL_NAMESPACE
