#!/usr/bin/env python
# encoding: utf-8
#
# Copyright © 2019, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Base functionality for all services."""

import logging
import time

import six
from six.moves.urllib_parse import quote

from .. import core
from ..core import HTTPError, sasctl_command
from ..exceptions import JobTimeoutError


class Service(object):
    """Base class for all services.  Should not be used directly."""

    _SERVICE_ROOT = None

    is_uuid = staticmethod(core.is_uuid)
    get_link = staticmethod(core.get_link)
    request_link = staticmethod(core.request_link)

    log = logging.getLogger(__name__)

    @property
    def _SERVICE_ROOT(self):
        raise NotImplementedError()

    @classmethod
    def is_available(cls):
        """Check if the service is currently available.

        Returns
        -------
        bool

        """
        response = cls.head('/', raw=True)
        return response.status_code == 200

    @classmethod
    def info(cls):
        """Version and build information for the service.

        Returns
        -------
        RestObj

        """
        return cls.get('/apiMeta')

    @classmethod
    def request(cls, verb, path, session=None, raw=False, **kwargs):
        """Send an HTTP request with a session.

        Parameters
        ----------
        verb : str
            A valid HTTP request verb.
        path : str
            Path portion of URL to request.  Assumed to be relative to
            `_SERVICE_ROOT`.
        session : Session, optional
            Defaults to `current_session()`.
        raw : bool
            Whether to return the raw `Response` object.  Defaults to False.
        kwargs : any

        Returns
        -------

        """
        session = session or core.current_session()

        if session is None:
            raise TypeError('No `Session` instance found.')

        if path.startswith('/'):
            path = cls._SERVICE_ROOT + path
        else:
            path = cls._SERVICE_ROOT + '/' + path

        response = session.request(verb, path, **kwargs)

        if 400 <= response.status_code <= 599:
            raise HTTPError(response.url, response.status_code,
                            response.text, response.headers, None)

        if raw:
            return response

        try:
            if raw:
                return response.json()
            else:
                obj = core._unwrap(response.json())

                # ETag is required to update any object
                # May not be returned on all responses (e.g. listing
                # multiple objects)
                if isinstance(obj, core.RestObj):
                    obj._headers = response.headers
                return obj
        except ValueError:
            return response.text

    @classmethod
    def get(self, *args, **kwargs):
        """Send a GET request."""
        try:
            return self.request('get', *args, **kwargs)
        except HTTPError as e:
            if e.code == 404:
                return None  # Resource not found
            else:
                raise e

    @classmethod
    def head(cls, *args, **kwargs):
        """Send a HEAD request."""
        return cls.request('head', *args, **kwargs)

    @classmethod
    def post(cls, *args, **kwargs):
        """Send a POST request."""
        return cls.request('post', *args, **kwargs)

    @classmethod
    def put(cls, *args, **kwargs):
        """Send a PUT request."""
        return cls.request('put', *args, **kwargs)

    @classmethod
    def delete(cls, *args, **kwargs):
        """Send a DELETE request."""
        return cls.request('delete', *args, **kwargs)

    @staticmethod
    def _crud_funcs(path,
                    single_term=None,
                    plural_term=None,
                    service_name=None,
                    get_filter=None):
        """Utility method for defining CRUD functions.

        Can be used to define simple functions that perform CRUD operations
        on a REST endpoint.

        Parameters
        ----------
        path : str
            URL path to use for the requests
        single_term : str
            English name of the item being manipulated.
            Defaults to `plural_term`.
        plural_term : str
            English name of the items being manipulated. Defaults to the last
            segment of `path`.
        service_name : str
            Name of the service under which the command will be listed in
            the `sasctl` CLI.  Defaults to `plural_term`.
        get_filter : callable, optional
            A function that accepts an `item` and returns a dictionary
            representing quary parameters to be added to the request for
            filtering.  Defaults to filter=eq(name, item.name).

        Returns
        -------
        functions : tuple
            tuple of `classmethod` instances representating CRUD functions:
            list_items, get_item, update_item, delete_item

        Examples
        --------

        >>> list_spam, get_spam, update_spam, delete_spam = _build_crud_funcs('/spam')

        """
        # Set a default filter
        if get_filter is None:
            def get_filter(item):
                return dict(filter='eq(name, "%s")' % item)

        @sasctl_command('list')
        def list_items(cls, filter=None, start=None, limit=None, **kwargs):
            """List all {items} available in the environment.

            Parameters
            ----------
            filter : str, optional
            start : int, optional
                Zero-based index of the first item to return.  Defaults to 0.
            limit : int, optional
                The maximum number of items to return.  Defaults to 20.

            Returns
            -------
            list
                A list of dictionaries containing the {items}.

            Notes
            -----
            See the filtering_ reference for details on the `filter` parameter.

            .. _filtering: https://developer.sas.com/reference/filtering/

            """
            if filter is not None:
                kwargs['filter'] = filter
            if start is not None:
                kwargs['start'] = int(start)
            if limit is not None:
                kwargs['limit'] = int(limit)

            params = '&'.join(['%s=%s' % (k, quote(str(v), safe='/(),"'))
                               for k, v in six.iteritems(kwargs)])

            results = cls.get(path, params=params)
            if results is None:
                return []
            else:
                return results if isinstance(results, list) else [results]

        @sasctl_command('get')
        def get_item(cls, item, refresh=False):
            """Return a {item} instance.

            Parameters
            ----------
            item : str or dict
                Name, ID, or dictionary representation of the {item}.
            refresh : bool, optional
                Obtain an updated copy of the {item}.

            Returns
            -------
            RestObj or None
                A dictionary containing the {item} attributes or None.

            Notes
            -------
            If `item` is a complete representation of the {item} it will be
            returned unless `refresh` is set.  This prevents unnecessary REST
            calls when data is already available on the client.

            """
            # If the input already appears to be the requested object just
            # return it, unless a refresh of the data was explicitly requested.
            if isinstance(item, dict) and all(
                    [k in item for k in ('id', 'name')]):
                if refresh:
                    item = item['id']
                else:
                    return item

            if cls.is_uuid(item):
                return cls.get(path + '/{id}'.format(id=item))
            else:
                results = list_items(cls, **get_filter(item))

                # Not sure why, but as of 19w04 the filter doesn't seem to work
                for result in results:
                    if result['name'] == str(item):
                        # Make a request for the specific object so that ETag
                        # is included, allowing updates.
                        if cls.get_link(result, 'self'):
                            return cls.request_link(result, 'self')
                        else:
                            id = result.get('id', result['name'])
                        return cls.get(path + '/{id}'.format(id=id))

                return None

            assert item is None or isinstance(item, dict)
            return item

        @sasctl_command('update')
        def update_item(cls, item):
            """Update a {item} instance.

            Parameters
            ----------
            item : dict

            Returns
            -------
            None

            """
            headers = getattr(item, '_headers', None)
            if headers is None or headers.get('etag') is None:
                raise ValueError(
                    'Could not find ETag for update of %s.' % item)

            id = getattr(item, 'id', None)
            if id is None:
                raise ValueError(
                    'Could not find property `id` for update of %s.' % item)

            headers = {'If-Match': item._headers.get('etag'),
                       'Content-Type': item._headers.get('content-type')}

            return cls.put(path + '/%s' % id, json=item, headers=headers)

        @sasctl_command('delete')
        def delete_item(cls, item):
            """Delete a {item} instance.

            Parameters
            ----------
            item

            Returns
            -------
            None

            """
            item_name = str(item)

            # Try to find the item if the id can't be found
            if not (isinstance(item, dict) and 'id' in item):
                item = get_item(cls, item)
                if item is None:
                    cls.log.info("Object '%s' not found.  Skipping delete."
                                 % item_name)
                    return

            if isinstance(item, dict) and 'id' in item:
                item = item['id']

            if cls.is_uuid(item):
                return cls.delete(path + '/{id}'.format(id=item))
            else:
                raise ValueError("Unrecognized id '%s'" % item)

        # Pull object name from path if unspecified (many paths end in
        # nouns like /folders or /repositories).
        plural_term = plural_term or str(path).split('/')[-1]
        single_term = single_term or plural_term
        service_name = service_name or plural_term
        service_name = service_name.replace(' ', '_')

        for func in [list_items, get_item, update_item, delete_item]:
            func.__doc__ = func.__doc__.format(item=single_term,
                                               items=plural_term)
            func._cli_service = service_name

            prefix = func.__name__.split('_')[0] + '_'
            suffix = plural_term if prefix == 'list_' else single_term
            func.__name__ = prefix + suffix

        return [classmethod(f) for f in
                (list_items, get_item, update_item, delete_item)]

    def _get_rel(self, item, rel, func=None, filter=None, *args):
        """Get `item` and request a link.

        Parameters
        ----------
        item : str or dict
        rel : str
        func : function, optional
            Callable that takes (item, *args) and returns a RestObj of `item`
        filter : str, optional

        args : any
            Passed to `func`

        Returns
        -------
        list

        """
        if func is not None:
            obj = func(item, *args)

        if obj is None:
            return

        params = 'filter={}'.format(filter) if filter is not None else {}

        resources = self.request_link(obj, rel, params=params)
        return resources if isinstance(resources, list) else [resources]

    @classmethod
    def _monitor_job(cls, job, max_retries=60):
        """Continually poll a job until it reaches the desired status.

        Parameters
        ----------
        job : dict
            Dictionary representation of a currently execution job
        max_retries : int
            Maximum number of ties to refresh `job` before failing.

        Returns
        -------
        job

        Raises
        ------
        TimeoutError
            `max_retries` reached with a successful status check

        """
        def completed(job):
            return job['state'].lower() in ('completed', 'failed')

        retries = 0

        if cls.get_link(job, 'self') is None:
            raise ValueError("Link 'self' not found on %s" % job)

        # TODO: Log
        while not completed(job) and retries < max_retries:
            time.sleep(0.5)
            retries += 1
            job = cls.request_link(job, 'self')

        if completed(job):
            return job
        else:
            raise JobTimeoutError('Timeout while waiting on job %s' % job)
