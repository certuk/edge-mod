import pymongo

from edge.inbox import InboxProcessorForPackages, InboxProcessorForBuilders, InboxItem, InboxError, anti_ping_pong, \
    drop_envelopes, INBOX_DROP_ENVELOPES
from edge.generic import create_package, EdgeObject
from mongoengine.connection import get_db
from adapters.certuk_mod.validation import ValidationStatus
from adapters.certuk_mod.validation.package.validator import PackageValidationInfo
from .ttp_capec_finder import capec_finder
from edge.tools import rgetattr
from .edges import dedup_collections
from edge import LOCAL_NAMESPACE

PROPERTY_TYPE = ['api_object', 'obj', 'object_', 'properties', '_XSI_TYPE']
PROPERTY_FILENAME = ['api_object', 'obj', 'object_', 'properties', 'file_name']
PROPERTY_MD5 = ['api_object', 'obj', 'object_', 'properties', 'md5']
PROPERTY_SHA1 = ['api_object', 'obj', 'object_', 'properties', 'sha1']
PROPERTY_SHA224 = ['api_object', 'obj', 'object_', 'properties', 'sha224']
PROPERTY_SHA256 = ['api_object', 'obj', 'object_', 'properties', 'sha256']
PROPERTY_SHA384 = ['api_object', 'obj', 'object_', 'properties', 'sha384']
PROPERTY_SHA512 = ['api_object', 'obj', 'object_', 'properties', 'sha512']
PROPERTY_CAPEC = ['api_object', 'obj', 'behavior', '_attack_patterns']

def _get_sighting_count(obs):
    sighting_count = getattr(obs, 'sighting_count', 1)
    if sighting_count is None:
        sighting_count = 1
    return sighting_count


def _merge_properties(api_object, id_, count, additional_file_hashes):
    api_object.obj.sighting_count = _get_sighting_count(api_object.obj) + count
    if id_ in additional_file_hashes:
        file_properties = rgetattr(api_object, ['obj', 'object_', 'properties'], None)
        for hash_type, hash_value in additional_file_hashes[id_].iteritems():
            if getattr(file_properties, hash_type, None) is None:
                setattr(file_properties, hash_type, hash_value)


def _update_existing_properties(additional_sightings, additional_file_hashes, user):
    inbox_processor = InboxProcessorForBuilders(user=user)
    for id_, count in additional_sightings.iteritems():
        edge_object = EdgeObject.load(id_)
        api_object = edge_object.to_ApiObject()
        _merge_properties(api_object, id_, count, additional_file_hashes)
        inbox_processor.add(InboxItem(
                api_object=api_object,
                etlp=edge_object.etlp,
                etou=edge_object.etou,
                esms=edge_object.esms
        ))
    inbox_processor.run()


def _coalesce_duplicates(contents, map_table):
    def add_missing_file_hash(inbox_object, file_hashes, property_name):
        hash_type = property_name[-1]
        if hash_type not in file_hashes:
            hash_value = rgetattr(inbox_object, property_name, None)
            if hash_value is not None:
                file_hashes[hash_type] = hash_value

    out = {}
    additional_sightings = {}
    additional_file_hashes = {}
    for id_, io in contents.iteritems():
        if id_ not in map_table:
            io.api_object = io.api_object.remap(map_table)
            out[id_] = io
        elif io.api_object.ty == 'obs':
            existing_id = map_table[id_]
            sightings_for_duplicate = _get_sighting_count(io.api_object.obj)
            additional_sightings[existing_id] = additional_sightings.get(existing_id, 0) + sightings_for_duplicate
            if rgetattr(io, PROPERTY_TYPE, None) == 'FileObjectType':
                if existing_id not in additional_file_hashes:
                    additional_file_hashes[existing_id] = {}
                add_missing_file_hash(io, additional_file_hashes[existing_id], PROPERTY_MD5)
                add_missing_file_hash(io, additional_file_hashes[existing_id], PROPERTY_SHA1)
                add_missing_file_hash(io, additional_file_hashes[existing_id], PROPERTY_SHA224)
                add_missing_file_hash(io, additional_file_hashes[existing_id], PROPERTY_SHA256)
                add_missing_file_hash(io, additional_file_hashes[existing_id], PROPERTY_SHA384)
                add_missing_file_hash(io, additional_file_hashes[existing_id], PROPERTY_SHA512)
    return out, additional_sightings, additional_file_hashes


def _generate_message(template_text, contents, out):
    removed = len(contents) - len(out)
    message = (template_text % removed) if removed else None
    return message


def _find_matching_db_file_obs(db, new_file_obs):
    def extract_properties(inbox_items, property_path):
        return list({str(rgetattr(inbox_item, property_path, None)) for inbox_item in inbox_items.itervalues()
                     if rgetattr(inbox_item, property_path, None) is not None})

    new_filenames = extract_properties(new_file_obs, PROPERTY_FILENAME)
    new_md5s = extract_properties(new_file_obs, PROPERTY_MD5)
    new_sha1s = extract_properties(new_file_obs, PROPERTY_SHA1)
    new_sha224s = extract_properties(new_file_obs, PROPERTY_SHA224)
    new_sha256s = extract_properties(new_file_obs, PROPERTY_SHA256)
    new_sha384s = extract_properties(new_file_obs, PROPERTY_SHA384)
    new_sha512s = extract_properties(new_file_obs, PROPERTY_SHA512)
    existing_file_obs = db.stix.find({
        'type': 'obs',
        'data.api.object.properties.xsi:type': 'FileObjectType',
        '$or': [
            {
                'data.api.object.properties.file_name': {'$in': new_filenames}
            }, {
                '$and': [
                    {'data.api.object.properties.hashes.type': 'MD5'},
                    {'data.api.object.properties.hashes.simple_hash_value': {'$in': new_md5s}}
                ]
            }, {
                '$and': [
                    {'data.api.object.properties.hashes.type': 'SHA1'},
                    {'data.api.object.properties.hashes.simple_hash_value': {'$in': new_sha1s}}
                ]
            }, {
                '$and': [
                    {'data.api.object.properties.hashes.type': 'SHA224'},
                    {'data.api.object.properties.hashes.simple_hash_value': {'$in': new_sha224s}}
                ]
            }, {
                '$and': [
                    {'data.api.object.properties.hashes.type': 'SHA256'},
                    {'data.api.object.properties.hashes.simple_hash_value': {'$in': new_sha256s}}
                ]
            }, {
                '$and': [
                    {'data.api.object.properties.hashes.type': 'SHA384'},
                    {'data.api.object.properties.hashes.simple_hash_value': {'$in': new_sha384s}}
                ]
            }, {
                '$and': [
                    {'data.api.object.properties.hashes.type': 'SHA512'},
                    {'data.api.object.properties.hashes.simple_hash_value': {'$in': new_sha512s}}
                ]
            }
        ]
    }).sort('created_on', pymongo.DESCENDING)
    return existing_file_obs


def _is_matching_file(existing_file, new_file):
    def matches(existing, new, property_path):
        # NOTE: need to ignore the `api_object` part of the property path here - hence `[1:]`
        existing_value = rgetattr(existing, property_path[1:], None)
        new_value = rgetattr(new, property_path[1:], None)
        return existing_value is not None and new_value is not None and existing_value == new_value

    return matches(existing_file, new_file, PROPERTY_FILENAME) and (
        matches(existing_file, new_file, PROPERTY_MD5) or
        matches(existing_file, new_file, PROPERTY_SHA1) or
        matches(existing_file, new_file, PROPERTY_SHA224) or
        matches(existing_file, new_file, PROPERTY_SHA256) or
        matches(existing_file, new_file, PROPERTY_SHA384) or
        matches(existing_file, new_file, PROPERTY_SHA512)
    )


def _add_matching_file_observables(db, map_table, contents):
    # identify file observables in contents excluding any which are already in map_table
    new_file_obs = {id_: inbox_item for (id_, inbox_item) in contents.iteritems()
                    if inbox_item.api_object.ty == 'obs' and
                    id_ not in map_table and  # exclude perfect matches which have already been discovered via data hash
                    rgetattr(inbox_item, PROPERTY_TYPE, 'Unknown') == 'FileObjectType'}
    if not new_file_obs:
        # if we have no new file observables, we can bail out
        return

    existing_file_obs = _find_matching_db_file_obs(db, new_file_obs)
    if not existing_file_obs:
        # if we have no matching existing file observables, we can bail out
        return

    for existing_file in existing_file_obs:
        for (new_id, new_file) in new_file_obs.iteritems():
            if _is_matching_file(EdgeObject(existing_file).to_ApiObject(), new_file.api_object):
                map_table[new_id] = existing_file['_id']


def _existing_hash_dedup(contents, hashes, user):
    db = get_db()

    existing_items = db.stix.find({
        'type': 'obs',
        'data.hash': {
            '$in': hashes.values()
        }
    }, {
        '_id': 1,
        'data.hash': 1
    }).sort('created_on', pymongo.DESCENDING)

    hash_to_existing_ids = {doc['data']['hash']: doc['_id'] for doc in existing_items}

    map_table = {
        id_: hash_to_existing_ids[hash_] for id_, hash_ in hashes.iteritems() if hash_ in hash_to_existing_ids
        }

    # file observable have more complex rules for duplicates, so simple hash matching isn't good enough
    _add_matching_file_observables(db, map_table, contents)

    out, additional_sightings, additional_file_hashes = _coalesce_duplicates(contents, map_table)

    if additional_sightings:
        _update_existing_properties(additional_sightings, additional_file_hashes, user)

    message = _generate_message("Remapped %d observables to existing observables based on hashes", contents, out)

    return out, message


def _new_hash_dedup(contents, hashes, user):
    hash_to_ids = {}
    for id_, hash_ in sorted(hashes.iteritems()):
        if rgetattr(contents.get(id_, None), ['api_object', 'ty'], '') == 'obs':
            hash_to_ids.setdefault(hash_, []).append(id_)

    map_table = {}
    for hash_, ids in hash_to_ids.iteritems():
        if len(ids) > 1:
            master = ids[0]
            for dup in ids[1:]:
                map_table[dup] = master

    out, additional_sightings, additional_file_hashes = _coalesce_duplicates(contents, map_table)

    for id_, count in additional_sightings.iteritems():
        inbox_item = contents.get(id_, None)
        if inbox_item is not None:
            api_object = inbox_item.api_object
            _merge_properties(api_object, id_, count, additional_file_hashes)

    message = _generate_message("Merged %d observables in the supplied package based on hashes", contents, out)

    for id_, io in out.iteritems():
        dedup_collections(io.api_object.ty, io.api_object.obj)

    return out, message

def flatten_ttp_capecs(io):
    flattened_capecs = {}
    for length, ttps in io.iteritems():
        for ttp in ttps:
            ids = []
            for capecs in ttp.api_object.obj.behavior.attack_patterns:
                if capecs.capec_id != None:
                    ids.append(capecs.capec_id)
            if len(ids) != 0:
                join = ",".join(sorted(ids))
                key = ttp.api_object.obj.title.strip().lower() + ": " + join
                flattened_capecs.setdefault(len(ids), []).append({ttp.id: key})
    return flattened_capecs

def coalesce_ttps(contents, map_table):
    out = {}
    for id_, io in contents.iteritems():
        if id_ not in map_table:
            io.api_object = io.api_object.remap(map_table)
            out[id_]= io
    return out

def ttp_title_capecs_to_ids(ids_to_capecs, amount_of_ttps):
    title_and_capecs_to_ids = {}
    for length, ttps in ids_to_capecs.iteritems():
        if len(ttps) > amount_of_ttps:
            for ttp in ttps:
                for id, key in ttp.iteritems():
                    title_and_capecs_to_ids.setdefault(key, []).append(id)
    return title_and_capecs_to_ids

def CERT_package_ttps_with_capec(contents, local_only):
    number_of_capecs_to_objects = {}
    for id_, io in sorted(contents.iteritems()):
        is_local = rgetattr(contents.get(id_, None), ['api_object', 'obj', 'id_ns'], '') == LOCAL_NAMESPACE
        correct_ns = is_local if local_only else (not is_local)
        if rgetattr(contents.get(id_, None), ['api_object', 'ty'], '') == 'ttp' and \
                        len(rgetattr(contents.get(id_, None), PROPERTY_CAPEC, '')) > 0 and correct_ns:
            amount_of_capecs = len(io.api_object.obj.behavior._attack_patterns)
            number_of_capecs_to_objects.setdefault(amount_of_capecs, []).append(io)
    return number_of_capecs_to_objects

def _existing_ttp_capec_dedup(contents, hashes, user, local):
    existing_ttps = capec_finder(local)

    id_to_title = {}
    existing_id_to_capec = {}
    for found_data in existing_ttps:
        capmans = []
        for work in found_data['capecs']:
            capmans.append(work['capec'])
            existing_id_to_capec[found_data['_id']] = capmans
            id_to_title[found_data['_id']] = work['title']

    existing_title_and_capecs = {}
    for ids, capecs in existing_id_to_capec.iteritems():
        join = ",".join(sorted(capecs))
        title = id_to_title[ids].lower().strip()
        key = title + ": " + join
        existing_title_and_capecs[key] = ids

    ttps_to_compare = CERT_package_ttps_with_capec(contents, local)
    ids_to_capecs = flatten_ttp_capecs(ttps_to_compare)

    title_and_capecs_to_ids = {}
    for length, ttps in ids_to_capecs.iteritems():
            for ttp in ttps:
                for id, key in ttp.iteritems():
                    title_and_capecs_to_ids[key] = id


    map_table = {
        id_: existing_title_and_capecs[key] for key, id_ in title_and_capecs_to_ids.iteritems() if key in existing_title_and_capecs
    }

    out = coalesce_ttps(contents, map_table)
    if local:
        message = _generate_message("Remapped %d CERUK namespace TTPs to existing TTPs based on CAPEC-IDs and title", contents, out)
    else:
        message = _generate_message("Remapped %d external namespace TTPs to existing TTPs based on CAPEC-IDs and title", contents, out)
    return out, message

def _new_ttp_capec_dedup(contents, hashes, user, local):
    number_of_capecs_to_objects = CERT_package_ttps_with_capec(contents, local)

    ids_to_capecs = flatten_ttp_capecs(number_of_capecs_to_objects)

    title_and_capecs_to_ids = ttp_title_capecs_to_ids(ids_to_capecs, 1)

    map_table = {}
    for capec, ids in title_and_capecs_to_ids.iteritems():
        if len(ids) > 1:
            master = ids[0]
            for dup in ids[1:]:
                map_table[dup] = master

    out = coalesce_ttps(contents, map_table)

    if local:
        message = _generate_message("Merged %d CERTUK namespace TTPs in the supplied package based on CAPEC-IDs and title", contents, out)
    else:
        message = _generate_message("Merged %d external namespace TTPs in the supplied package based on CAPEC-IDs and title", contents, out)
    return out, message

def _new_ttp_CERT_capec_dedup(contents, hashes, user):
    return _new_ttp_capec_dedup(contents, hashes, user, True)

def _new_ttp_external_capec_dedup(contents, hashes, user):
    return _new_ttp_capec_dedup(contents, hashes, user, False)

def _existing_ttp_CERT_capec_dedup(contents, hashes, user):
    return _existing_ttp_capec_dedup(contents, hashes, user, True)

def _existing_ttp_external_capec_dedup(contents, hashes, user):
    return _existing_ttp_capec_dedup(contents, hashes, user, False)

class DedupInboxProcessor(InboxProcessorForPackages):
    filters = ([drop_envelopes] if INBOX_DROP_ENVELOPES else []) + [
        _new_hash_dedup,  # removes new STIX objects matched by hash
        _existing_hash_dedup,  # removes existing STIX objects matched by hash
        _new_ttp_CERT_capec_dedup,  # removes new STIX TTP objects matched by CAPEC-IDs and Title in CERT NS
        _existing_ttp_CERT_capec_dedup, # removes existing STIX TTP objects matched by CAPEC-IDs and Title in CERT NS
        _new_ttp_external_capec_dedup, # removes new STIX TTP objects matched by CAPEC-IDs and Title in external NS
        _existing_ttp_external_capec_dedup, # removes existing STIX TTP objects matched by CAPEC-IDs and Title in external NS
        anti_ping_pong,  # removes existing STIX objects matched by id
    ]

    def __init__(self, user, trustgroups=None, streams=None, validate=True):
        super(DedupInboxProcessor, self).__init__(user, trustgroups, streams)
        self.validation_result = {}
        self.package_header = DedupInboxProcessor.get_package_header(self.contents)
        self.validate = validate

    @staticmethod
    def get_package_header(contents):
        if contents:
            package_items = {id_: inbox_item for id_, inbox_item in contents.iteritems() if
                             inbox_item.api_object.ty == 'pkg'}

            related_package_ids = set()
            for package_item in package_items.values():
                if package_item.api_object.obj.related_packages:
                    related_packages = package_item.api_object.obj.related_packages
                    related_package_ids = related_package_ids.union(
                            {related_package.item.idref for related_package in related_packages})

            top_level_package_ids = set(package_items.keys()).difference(related_package_ids)
            if len(top_level_package_ids) > 1:
                raise InboxError("Multiple top level packages are not expected")
            if len(top_level_package_ids) == 0:
                return None

            top_level_package_item = package_items[top_level_package_ids.pop()]
            return top_level_package_item.api_object.obj.stix_header

        return None

    @staticmethod
    def _validate(contents, package_header):
        if not contents:
            return None
        # At this point, only things that don't already exist in the database will be in contents...
        # We can exclude packages, as they only serve as containers for other objects.
        contents_to_validate = {
            id_: inbox_item.api_object for id_, inbox_item in contents.iteritems() if inbox_item.api_object.ty != 'pkg'
            }
        # Wrap the contents in a package for convenience so they can be easily validated:
        package_for_validation = create_package(contents_to_validate)
        package_for_validation.stix_header = package_header
        validation_result = PackageValidationInfo.validate(package_for_validation)

        return validation_result.validation_dict

    def apply_filters(self):
        super(DedupInboxProcessor, self).apply_filters()
        if not self.contents or not self.validate:
            return
        self.validation_result = DedupInboxProcessor._validate(self.contents, self.package_header)
        for id_, object_fields in self.validation_result.iteritems():
            for field_name in object_fields:
                if object_fields[field_name]['status'] == ValidationStatus.ERROR:
                    raise InboxError('Validation failed')
