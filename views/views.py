import os
import re
import urllib2
import json
import datetime
from dateutil import tz
import requests

from django.http import FileResponse, HttpResponseNotFound
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt

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
import adapters.certuk_mod.builder.customizations as cert_builder

from adapters.certuk_mod.builder.kill_chain_definition import KILL_CHAIN_PHASES
from adapters.certuk_mod.common.views import activity_log, ajax_activity_log
from adapters.certuk_mod.common.logger import log_error, get_exception_stack_variable
from adapters.certuk_mod.cron import setup as cron_setup

from adapters.certuk_mod.cron.views import ajax_get_purge_task_status, ajax_run_purge
from adapters.certuk_mod.retention.views import ajax_get_retention_config, ajax_reset_retention_config, \
    ajax_set_retention_config
from adapters.certuk_mod.dedup.views import duplicates_finder, ajax_load_duplicates, ajax_load_object, \
    ajax_load_parent_ids, ajax_import
from adapters.certuk_mod.audit import setup as audit_setup, status
from adapters.certuk_mod.audit.event import Event
from adapters.certuk_mod.audit.handlers import log_activity
from adapters.certuk_mod.audit.message import format_audit_message
from adapters.certuk_mod.retention.purge import STIXPurge
from adapters.certuk_mod.validation import FieldValidationInfo, ValidationStatus
from users.models import Repository_User

audit_setup.configure_publisher_actions()
cert_builder.apply_customizations()
cron_setup.create_jobs()

objectid_matcher = re.compile(
        # {STIX/ID Alias}:{type}-{GUID}
        r".*/([a-z][\w\d-]+:[a-z]+-[a-f\d]{8}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{12})/?$",
        re.IGNORECASE  # | re.DEBUG
)


@login_required
def static(request, path):
    clean_path = urllib2.unquote(path)
    if "../" not in clean_path:
        return FileResponse(
                open(os.path.dirname(__file__) + "/../static/" + clean_path, mode="rb")
        )
    else:
        return HttpResponseNotFound()


@login_required
def discover(request):
    referrer = urllib2.unquote(request.META.get("HTTP_REFERER", ""))
    match = objectid_matcher.match(referrer)
    if match is not None and len(match.groups()) == 1:
        id_ = match.group(1)
        return redirect("publisher_review", id_=id_)
    else:
        return redirect("publisher_not_found")

from ioc_parser.iocp import IOC_Parser
@login_required
def extract(request):
    request.breadcrumbs([("Extract Stix", "")])
    return render(request, "extract_upload_form.html")

from django.core.files.base import ContentFile

import contextlib
@contextlib.contextmanager
def capture():
    import sys
    from cStringIO import StringIO
    oldout,olderr = sys.stdout, sys.stderr
    try:
        out=[StringIO(), StringIO()]
        sys.stdout,sys.stderr = out
        yield out
    finally:
        sys.stdout,sys.stderr = oldout, olderr
        out[0] = out[0].getvalue()
        out[1] = out[1].getvalue()

import xml.etree.ElementTree as ET
from copy import copy

def dictify(r,root=True):
    if root:
        return {r.tag : dictify(r, False)}
    d=copy(r.attrib)
    if r.text:
        d["_text"]=r.text
    for x in r.findall("./*"):
        if x.tag not in d:
            d[x.tag]=[]
        d[x.tag].append(dictify(x,False))
    return d

from adapters.certuk_mod.dedup.DedupInboxProcessor import DedupInboxProcessor
from StringIO import StringIO
from edge.inbox import InboxItem
from edge import IDManager
from users.models import Draft
from stix.utils import set_id_namespace
from edge.generic import EdgeObject
from edge.generic import create_package
from edge.inbox import InboxProcessorForBuilders
from edge.inbox import InboxProcessorForPackages
@csrf_exempt
@login_required
def extract_upload(request):
    file_import = request.FILES['import']
    parser = IOC_Parser(None, 'pdf', True, "pypdf2", "stix");

    xml_contents = None
    with capture() as out:
        NAMESPACE = {"http://www.purplesecure.com" : "pss"}
        set_id_namespace(NAMESPACE)
        parser.parse_pdf_pypdf2(file_import, "")
        xml_contents = ET.fromstring(out[0].getvalue())
        stream = StringIO(out[0].getvalue())
        upload_id = 9999

    ip = InboxProcessorForPackages(user=request.user, streams=[(stream, None)])
    indicators = [inbox_item for id, inbox_item in ip.contents.iteritems() if inbox_item.api_object.ty == 'ind']
    count = 0
    urls = []
    for indicator in indicators:
        indicator.api_object.obj.title = "StixPDFExtract" + str(count)
        count += 1
        urls.append(request.META['HTTP_ORIGIN']+ "/" + TYPE_TO_URL[indicator.api_object.ty] + "/edit/" + indicator.id)

    ip.run()

    #draft_urls = []

    #ids_to_delete = [id for id, inbox_item in ip.contents.iteritems()]

    #count = 0
    #for indicator in indicators:
    #
    #    loaded_indicator = EdgeObject.load(indicator.id)
    #    loaded_indicator.obj.title = "StixPDFExtract" + str(count)
    #
    #    #Draft.upsert('ind', loaded_indicator.to_draft(), request.user),
    #
    #    count += 1
    #    print "drafting:  " + loaded_indicator.id_ + "\n"
        #draft_urls.append(request.META['HTTP_ORIGIN']+ "/" + TYPE_TO_URL[loaded_indicator.ty] + "/build/" + loaded_indicator.id_)

    #for page_index in range(0, len(ids_to_delete), 10):
    #    try:
    #        chunk_ids = ids_to_delete[page_index: page_index + 10]
    #        STIXPurge.remove(chunk_ids)
    #    except Exception as e:
    #        log_activity('system', 'AGEING', 'ERROR', e.message)


    return render(request, "extract_upload_complete.html", { 'result' :urls});

    #for inbox_item in sorted_items:
    #    #inbox_item.api_object.obj.title = "test_obj"
    #    indicator = {}
    #    indicator['title'] = "stix_upload"
    #    indicator['id_ns'] =  inbox_item.api_object.obj.id_ns
    #    indicator['composition_type'] = inbox_item.api_object.obj.observable_composition_operator
    #
    #    observables = []
    #    obs_comp = ip.contents.get(inbox_item.api_object.obj.observables[0].idref)
    #    for obs in obs_comp.api_object.obj._observable_composition.observables:
    #        actual_obs = ip.contents.get(obs._idref)
    #
    #        child_obs = {}
    #        child_obs['description'] = actual_obs['description']
    #        child_obs['title'] = actual_obs['title']
    #
    #        observables.append(child_obs)
    #
    #    indicator['observables'] = observables

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
    referrer = urllib2.unquote(request.META.get("HTTP_REFERER", ""))
    match = objectid_matcher.match(referrer)
    try:
        if match is not None and len(match.groups()) == 1:
            edge_object = EdgeObject.load(match.group(1))
            if edge_object.ty == 'obs':
                return not_clonable(request, "Observables cannot be cloned")
            new_id = IDManager().get_new_id(edge_object.ty)
            draft = edge_object.to_draft()
            draft['id'] = new_id
            Draft.upsert(edge_object.ty, draft, request.user)
            return redirect('/' + TYPE_TO_URL[edge_object.ty] + '/build/' + new_id, request)
        else:
            return not_clonable(request, "No clonable object found; please only choose the clone option from an object's summary or external publish page")
    except Exception as e:
        ext_ref_error = "not found"
        if e.message.endswith(ext_ref_error):
            return not_clonable(request, "Unable to load object as some external references were not found: " + e.message[0:-len(ext_ref_error)])
        else:
            return not_clonable(request, e.message)


@login_required
def not_clonable(request, msg):
    return render(request, "not_clonable.html", {"msg": msg})


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
