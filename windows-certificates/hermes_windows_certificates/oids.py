"""Object identifiers in words: signature and key algorithms, key purposes.

The maps carry the OIDs a real Windows store actually answers with; anything
else travels through with its dotted string and no name, so an unknown
algorithm is reported as unknown instead of guessed at.
"""

from __future__ import annotations

from typing import Dict, Optional

SIGNATURE_ALGORITHMS: Dict[str, str] = {
    "1.2.840.113549.1.1.4": "md5WithRSAEncryption",
    "1.2.840.113549.1.1.5": "sha1WithRSAEncryption",
    "1.2.840.113549.1.1.10": "RSASSA-PSS",
    "1.2.840.113549.1.1.11": "sha256WithRSAEncryption",
    "1.2.840.113549.1.1.12": "sha384WithRSAEncryption",
    "1.2.840.113549.1.1.13": "sha512WithRSAEncryption",
    "1.2.840.10045.4.1": "ecdsaWithSHA1",
    "1.2.840.10045.4.3.2": "ecdsaWithSHA256",
    "1.2.840.10045.4.3.3": "ecdsaWithSHA384",
    "1.2.840.10045.4.3.4": "ecdsaWithSHA512",
    "1.3.101.112": "Ed25519",
}

PUBLIC_KEY_ALGORITHMS: Dict[str, str] = {
    "1.2.840.113549.1.1.1": "RSA",
    "1.2.840.10045.2.1": "EC",
    "1.2.840.10040.4.1": "DSA",
    "1.3.101.112": "Ed25519",
}

KEY_PURPOSES: Dict[str, str] = {
    "1.3.6.1.5.5.7.3.1": "server authentication",
    "1.3.6.1.5.5.7.3.2": "client authentication",
    "1.3.6.1.5.5.7.3.3": "code signing",
    "1.3.6.1.5.5.7.3.4": "email protection",
    "1.3.6.1.5.5.7.3.5": "IPsec end system",
    "1.3.6.1.5.5.7.3.6": "IPsec tunnel",
    "1.3.6.1.5.5.7.3.7": "IPsec user",
    "1.3.6.1.5.5.7.3.8": "time stamping",
    "1.3.6.1.5.5.7.3.9": "OCSP signing",
    "2.5.29.37.0": "any purpose",
    "1.3.6.1.4.1.311.10.3.12": "document signing",
    "1.3.6.1.5.5.8.2.2": "IPsec IKE",
}

# named-curve OIDs travel inside the key algorithm's parameters; the DER body
# is matched by its content bytes so no ASN.1 parser is needed for the walk
_CURVE_CONTENT: Dict[bytes, str] = {
    b"\x2a\x86\x48\xce\x3d\x03\x01\x07": "P-256 (secp256r1)",
    b"\x2b\x81\x04\x00\x22": "P-384 (secp384r1)",
    b"\x2b\x81\x04\x00\x23": "P-521 (secp521r1)",
}
_CURVE_BITS: Dict[str, int] = {
    "P-256 (secp256r1)": 256,
    "P-384 (secp384r1)": 384,
    "P-521 (secp521r1)": 521,
}


def signature_name(oid: Optional[str]) -> Optional[str]:
    return SIGNATURE_ALGORITHMS.get(oid or "")


def public_key_name(oid: Optional[str]) -> Optional[str]:
    return PUBLIC_KEY_ALGORITHMS.get(oid or "")


def purpose_name(oid: str) -> Optional[str]:
    return KEY_PURPOSES.get(oid)


def curve_of(parameters: bytes) -> Optional[str]:
    """The named curve, matched by OID content bytes inside the parameters."""
    for content, name in _CURVE_CONTENT.items():
        if content in parameters:
            return name
    return None


def _der_tlv(blob: bytes, at: int):
    """``(content_start, content_length)`` of the DER TLV at ``at``.

    Handles the short and the long length form; ``None`` when the element runs
    off the end of ``blob``.
    """
    if at < 0 or at + 2 > len(blob):
        return None
    first = blob[at + 1]
    if first < 0x80:
        return at + 2, first
    count = first & 0x7F
    if count == 0 or at + 2 + count > len(blob):
        return None
    start = at + 2 + count
    length = int.from_bytes(blob[at + 2:at + 2 + count], "big")
    if start + length > len(blob):
        return None
    return start, length


def rsa_bit_length(public_key: bytes) -> Optional[int]:
    """Modulus size of a DER ``RSAPublicKey`` (SEQUENCE of two INTEGERs)."""
    if not public_key or public_key[0] != 0x30:
        return None
    seq = _der_tlv(public_key, 0)
    if seq is None:
        return None
    body_start, body_len = seq
    body = public_key[body_start:body_start + body_len]
    if not body or body[0] != 0x02:
        return None
    integer = _der_tlv(body, 0)
    if integer is None:
        return None
    modulus = body[integer[0]:integer[0] + integer[1]]
    if not modulus:
        return None
    # a leading 00 only keeps the sign bit clear; it is not a key bit
    return int.from_bytes(modulus, "big").bit_length()


def key_bits(algorithm_oid: Optional[str], public_key: bytes, parameters: bytes) -> Optional[int]:
    """The key size in bits, RSA from the modulus, EC from the named curve."""
    if algorithm_oid == "1.2.840.113549.1.1.1":
        return rsa_bit_length(public_key)
    if algorithm_oid == "1.2.840.10045.2.1":
        curve = curve_of(parameters)
        return _CURVE_BITS.get(curve) if curve else None
    return None


__all__ = [
    "KEY_PURPOSES",
    "PUBLIC_KEY_ALGORITHMS",
    "SIGNATURE_ALGORITHMS",
    "curve_of",
    "key_bits",
    "purpose_name",
    "public_key_name",
    "rsa_bit_length",
    "signature_name",
]
