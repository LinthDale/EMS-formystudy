"""Explicit certificate and TCP verification for the field DB connection."""
import ssl
from urllib.parse import parse_qsl,unquote,urlsplit


def validate_tls_files(value):
    if (not isinstance(value,dict) or set(value)!={'ca_file','cert_file','key_file'}
            or any(not isinstance(v,str) or not v.strip() for v in value.values())):
        raise ValueError('database TLS CA and client certificate/key required')


def verified_database_tls(dsn,files):
    validate_tls_files(files)
    url=urlsplit(dsn)
    query=parse_qsl(url.query,keep_blank_values=True)
    keys=[k for k,v in query]
    if (url.scheme not in ('postgres','postgresql') or not url.hostname
            or unquote(url.hostname).startswith('/') or ',' in url.hostname
            or len(keys)!=len(set(keys)) or any(k in keys for k in ('host','hostaddr','port'))
            or any(k=='sslmode' and v!='verify-full' for k,v in query)):
        raise ValueError('field database requires one verified TCP TLS endpoint')
    context=ssl.create_default_context(cafile=files['ca_file'])
    context.check_hostname=True;context.verify_mode=ssl.CERT_REQUIRED
    context.load_cert_chain(files['cert_file'],files['key_file'])
    return context
