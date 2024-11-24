import hashlib
from typing import Dict
from urllib.parse import parse_qs
from urllib.parse import urlencode
from urllib.parse import urlparse
from urllib.parse import urlunparse


def hash_str_to_int(text: str, N: int = 3):
    """Hash a string into an N-byte integer

    This method is used e.g. to convert the four-word style game identifiers into
    a database-friendly integer.
    """

    hash_obj = hashlib.md5(text.encode())
    hash_bytes = list(hash_obj.digest())

    # Slice off the first N bytes and cast to integer
    return int.from_bytes(hash_bytes[0:N], "big")


def add_params_to_url(url: str, params: Dict) -> str:
    """
    A chatGPT special to add parameters to a URL
    """

    parsed_url = urlparse(url)

    # Extract the query parameters as a dictionary
    query_params = parse_qs(parsed_url.query)

    # Add or update query parameters
    query_params = params

    # Encode the modified query parameters
    encoded_query = urlencode(query_params, doseq=True)

    # Reconstruct the URL with the modified query parameters
    return urlunparse(
        (
            parsed_url.scheme,
            parsed_url.netloc,
            parsed_url.path,
            parsed_url.params,
            encoded_query,
            parsed_url.fragment,
        )
    )
