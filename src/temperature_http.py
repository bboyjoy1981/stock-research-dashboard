"""Read public research releases without depending on one local proxy route."""

import requests


def get_public(url, **kwargs):
    """Try direct access, then the configured environment route on transport errors.

    HTTP errors such as 403 are returned to the caller and are never bypassed.
    """
    try:
        with requests.Session() as session:
            session.trust_env = False
            return session.get(url, **kwargs)
    except (requests.ConnectionError, requests.Timeout):
        return requests.get(url, **kwargs)
