# -*- coding: utf-8 -*-
#
# This file is part of Radicale Server - Calendar Server
# Copyright © 2008-2010 Guillaume Ayoub
# Copyright © 2008 Nicolas Kandel
# Copyright © 2008 Pascal Halter
#
# This library is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Radicale.  If not, see <http://www.gnu.org/licenses/>.

"""
Radicale Server module.

This module offers 3 useful classes:

- ``HTTPServer`` is a simple HTTP server;
- ``HTTPSServer`` is a HTTPS server, wrapping the HTTP server in a socket
  managing SSL connections;
- ``CalendarHTTPHandler`` is a CalDAV request handler for HTTP(S) servers.

To use this module, you should take a look at the file ``radicale.py`` that
should have been included in this package.

"""

# TODO: Manage errors (see xmlutils)

import base64
import socket
try:
    from http import client, server
except ImportError:
    import httplib as client
    import BaseHTTPServer as server

from radicale import acl, config, support, xmlutils

def check(request, function):
    """Check if user has sufficient rights for performing ``request``."""
    authorization = request.headers.get("Authorization", None)
    if authorization:
        challenge = authorization.lstrip("Basic").strip().encode("ascii")
        plain = request.decode(base64.b64decode(challenge))
        user, password = plain.split(":")
    else:
        user = password = None

    if request.server.acl.has_right(user, password):
        function(request)
    else:
        request.send_response(client.UNAUTHORIZED)
        request.send_header(
            "WWW-Authenticate",
            "Basic realm=\"Radicale Server - Password Required\"")
        request.end_headers()

# Decorator checking rights before performing request
check_rights = lambda function: lambda request: check(request, function)

class HTTPServer(server.HTTPServer):
    """HTTP server."""
    def __init__(self, address, handler):
        """Create server."""
        server.HTTPServer.__init__(self, address, handler)
        self.acl = acl.load()

class HTTPSServer(HTTPServer):
    """HTTPS server."""
    def __init__(self, address, handler):
        """Create server by wrapping HTTP socket in an SSL socket."""
        # Fails with Python 2.5, import if needed
        import ssl

        HTTPServer.__init__(self, address, handler)
        self.socket = ssl.wrap_socket(
            socket.socket(self.address_family, self.socket_type),
            server_side=True, 
            certfile=config.get("server", "certificate"),
            keyfile=config.get("server", "key"),
            ssl_version=ssl.PROTOCOL_SSLv23)
        self.server_bind()
        self.server_activate()

class CalendarHTTPHandler(server.BaseHTTPRequestHandler):
    """HTTP requests handler for calendars."""
    _encoding = config.get("encoding", "request")

    @property
    def calendar(self):
        """The ``calendar.Calendar`` object corresponding to the given path."""
        path = self.path.strip("/").split("/")
        if len(path) >= 2:
            cal = "%s/%s" % (path[0], path[1])
            return calendar.Calendar("radicale", cal)

    def decode(self, text):
        """Try to decode text according to various parameters."""
        # List of charsets to try
        charsets = []

        # First append content charset given in the request
        contentType = self.headers["Content-Type"]
        if contentType and "charset=" in contentType:
            charsets.append(contentType.split("charset=")[1].strip())
        # Then append default Radicale charset
        charsets.append(self._encoding)
        # Then append various fallbacks
        charsets.append("utf-8")
        charsets.append("iso8859-1")

        # Try to decode
        for charset in charsets:
            try:
                return text.decode(charset)
            except UnicodeDecodeError:
                pass
        raise UnicodeDecodeError

    @check_rights
    def do_GET(self):
        """Manage GET request."""
        answer = self.calendar.vcalendar.encode(_encoding)

        self.send_response(client.OK)
        self.send_header("Content-Length", len(answer))
        self.end_headers()
        self.wfile.write(answer)

    @check_rights
    def do_DELETE(self):
        """Manage DELETE request."""
        obj = self.headers.get("If-Match", None)
        answer = xmlutils.delete(obj, self.calendar, self.path)

        self.send_response(client.NO_CONTENT)
        self.send_header("Content-Length", len(answer))
        self.end_headers()
        self.wfile.write(answer)

    def do_OPTIONS(self):
        """Manage OPTIONS request."""
        self.send_response(client.OK)
        self.send_header("Allow", "DELETE, GET, OPTIONS, PROPFIND, PUT, REPORT")
        self.send_header("DAV", "1, calendar-access")
        self.end_headers()

    def do_PROPFIND(self):
        """Manage PROPFIND request."""
        xml_request = self.rfile.read(int(self.headers["Content-Length"]))
        answer = xmlutils.propfind(xml_request, self.calendar, self.path)

        self.send_response(client.MULTI_STATUS)
        self.send_header("DAV", "1, calendar-access")
        self.send_header("Content-Length", len(answer))
        self.end_headers()
        self.wfile.write(answer)

    @check_rights
    def do_PUT(self):
        """Manage PUT request."""
        ical_request = self.decode(
            self.rfile.read(int(self.headers["Content-Length"])))
        obj = self.headers.get("If-Match", None)
        xmlutils.put(ical_request, self.calendar, self.path, obj)

        self.send_response(client.CREATED)

    @check_rights
    def do_REPORT(self):
        """Manage REPORT request."""
        xml_request = self.rfile.read(int(self.headers["Content-Length"]))
        answer = xmlutils.report(xml_request, self.calendar, self.path)

        self.send_response(client.MULTI_STATUS)
        self.send_header("Content-Length", len(answer))
        self.end_headers()
        self.wfile.write(answer)
