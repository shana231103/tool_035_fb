"""Allowlisted Graph denial diagnostics; never retain provider payloads."""
import json
import logging

_CODES = {'ErrorAccessDenied', 'Authorization_RequestDenied', 'AuthenticationError',
          'InvalidAuthenticationToken', 'ErrorInvalidUser', 'ErrorMailboxNotEnabledForRESTAPI',
          'MailboxNotEnabledForRESTAPI', 'ErrorInvalidLicense'}


def graph_denial_reason(content, *, mailbox_operation):
    try:
        payload = json.loads(content)
        code = payload.get('error', {}).get('code')
    except (ValueError, UnicodeError, AttributeError, TypeError):
        code = None
    code = code if isinstance(code, str) and code in _CODES else 'UNKNOWN'
    logging.getLogger(__name__).warning('Graph access denied: operation=%s code=%s',
        'MAILBOX' if mailbox_operation else 'IDENTITY', code)
    if code in {'ErrorMailboxNotEnabledForRESTAPI', 'MailboxNotEnabledForRESTAPI', 'ErrorInvalidLicense'}:
        return 'MAILBOX_NOT_SUPPORTED'
    if code in {'AuthenticationError', 'InvalidAuthenticationToken'}:
        return 'GRAPH_AUTH_REJECTED'
    if code in {'ErrorAccessDenied', 'Authorization_RequestDenied'}:
        return 'GRAPH_ACCESS_DENIED'
    return 'GRAPH_ACCESS_DENIED'
