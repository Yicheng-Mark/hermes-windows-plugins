# hermes-windows-certificates

Answer **"which certificate on this machine expired, and what am I actually
trusting"** on Windows, from inside Hermes.

```python
win_cert_table({"expired_only": True})
win_cert_table({"query": "DigiCert"})
win_cert_detail({"thumbprint": "cdd4eeae6000ac7f401da5d6cf0b3b3a8887da77"})
```

The certificate stores are where TLS, code signing and mail encryption live or
die: an expired personal certificate breaks signing, a stale root chain breaks
TLS in ways a browser never shows, and nobody knows what a machine actually
trusts. These two tools read the stores and put the verdict in words.

## What the tools report

| Field | Where it comes from |
|---|---|
| `subject`, `issuer`, `friendly_name` | `CertGetNameStringW` on each certificate context |
| `valid_from`, `until`, `state`, `note` | the validity window, with the expiry in words — 'expired 45 days ago', 'expires in 12 days', 'valid for 300 more days' |
| `self_signed` | the subject and issuer DER blobs compared byte for byte (a root signs itself) |
| `thumbprint` | the SHA-1 hash property, the key `win_cert_detail` picks a certificate by |
| `serial`, `version` | the certificate's own fields; the serial is shown big-endian uppercase |
| `signature_algorithm` | mapped from its OID: sha256WithRSAEncryption, ecdsaWithSHA384, … |
| `public_key` | algorithm (RSA, EC), the named curve when there is one (P-256…), and the size in bits, read from the modulus or the curve |
| `purposes` | the EKU extension's OIDs in words — server authentication, code signing…; **no EKU extension is reported as 'does not restrict its purposes', which is what its absence means** |

`win_cert_table` walks the current user's and the machine's MY, Root and CA
stores (either scope alone on request), sorts the expired and soon-expiring
first, and filters by name substring, store, or `expired_only`. A Root store
carries self-signed certificates by design; the notes count them so a hundred
self-signed roots is not read as a hundred problems.

`win_cert_detail` finds one certificate by thumbprint (punctuation and case
ignored) or by a name substring; several matches come back as a candidate list
with thumbprints to pick from. The user's and the machine's copies of the same
certificate are both reported.

## Read-only, and why there is no subprocess

The stores are opened with `CERT_STORE_READONLY_FLAG` and only enumerated:
nothing is added, removed or changed, and there is no network call, no file
write, no elevation. Everything runs in-process through `crypt32` via `ctypes`
— `certutil`'s output follows the display language and a PowerShell session
costs a quarter of a second before the first row; this walk reads 121
certificates across both contexts and all three stores in about 8 ms. The
enumerator frees each context as it moves; every fact is copied out in Python
before the next step, and the plugin declares no Python dependencies.

Every `ctypes` prototype is declared with explicit `argtypes`/`restype` — on a
64-bit host an undeclared pointer argument is truncated and the call fails
silently. The `CERT_INFO` layout follows `wincrypt.h` field for field (Subject
sits after the two FILETIMEs there), so no offset is written by hand. Windows
only.
