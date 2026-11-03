"""Bounded transport, extracted from MoneyTalk's tested HTTP adapter."""
import http.client
import json
import socket
import ssl
from ipaddress import ip_address
from time import monotonic
from typing import Any
from urllib.parse import urlsplit
MAX_RESPONSE_BYTES=2*1024*1024

def post_json(
    url: str, headers: dict[str, str], body: dict[str, Any], timeout: int, *, local: bool
) -> tuple[int, dict[str, Any]]:
    """Bounded, no-redirect HTTP with the checked DNS address pinned to the socket.

    No environment proxy or netrc credentials are implicitly used.
    """
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not addresses:
        raise OSError("No endpoint address")
    for _, _, _, _, sockaddr in addresses:
        address = ip_address(sockaddr[0])
        if not (address.is_loopback if local else address.is_global):
            raise ValueError("Endpoint resolved to a disallowed address")
    family, socktype, proto, _, sockaddr = addresses[0]
    deadline = monotonic() + timeout
    sock = socket.socket(family, socktype, proto)
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    response = None
    try:
        sock.settimeout(timeout)
        sock.connect(sockaddr)
        if parsed.scheme == "https":
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
        connection.sock = sock
        encoded = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
        connection.request(
            "POST",
            parsed.path,
            encoded,
            {
                **headers,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        response = connection.getresponse()
        chunks: list[bytes] = []
        length = 0
        while not response.isclosed():
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError("Provider timed out")
            sock.settimeout(remaining)
            chunk = response.read1(min(65536, MAX_RESPONSE_BYTES + 1 - length))
            if not chunk:
                break
            chunks.append(chunk)
            length += len(chunk)
            if length > MAX_RESPONSE_BYTES:
                raise ValueError("Provider response exceeds size limit")
        # Never surface remote error bodies: they may echo keys or prompts.
        if response.status != 200:
            return response.status, {}
        payload = json.loads(b"".join(chunks))
        if not isinstance(payload, dict):
            raise ValueError("Provider response must be an object")
        return response.status, payload
    finally:
        if response is not None:
            response.close()
        connection.close()
        sock.close()



def get_text(url):
    """Public HTTPS GET, pin DNS, bound redirects and response size, no ambient credentials."""
    from urllib.parse import urljoin
    from .contracts import url as validate_url
    for _ in range(4):
        validate_url(url)
        parsed=urlsplit(url)
        addresses=socket.getaddrinfo(parsed.hostname,443,type=socket.SOCK_STREAM)
        if not addresses or any(not ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError('non_public_dns')
        family,kind,proto,_,address=addresses[0]
        raw=socket.socket(family,kind,proto)
        connection=http.client.HTTPConnection(parsed.hostname,443,timeout=20)
        try:
            raw.settimeout(20)
            raw.connect(address)
            connection.sock=ssl.create_default_context().wrap_socket(raw,server_hostname=parsed.hostname)
            connection.request('GET',parsed.path+('?' + parsed.query if parsed.query else ''),headers={'User-Agent':'MarketVoices/0.1 (research reader)'})
            response=connection.getresponse()
            if response.status in (301,302,303,307,308):
                url=urljoin(url,response.getheader('Location',''))
                continue
            if response.status!=200:
                raise ValueError('source_http_'+str(response.status))
            data=response.read(3_000_001)
            if len(data)>3_000_000:
                raise ValueError('source_too_large')
            return data.decode('utf-8-sig',errors='replace')
        finally:
            connection.close()
            raw.close()
    raise ValueError('too_many_redirects')
