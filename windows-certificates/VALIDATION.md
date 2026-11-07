# VALIDATION — hermes-windows-certificates

All numbers from the writing machine: Windows 11 Home China x64 (26100),
Python 3.13, unelevated user session, Chinese display language.

## Tests

- **28 passed** (20 unit + 8 live), full suite in 0.15 s:
  `python -m pytest tests/ -q`
- Unit layer runs on any OS: FILETIME math, the DER helpers (RSA modulus bits
  long-form and short-form, leading sign byte, truncated input rejected), the
  named-curve match, the OID words, the validity-word matrix (expired 45 days
  / less than a day / expires today / expiring / valid / not yet valid), both
  tools against faked stores (sorting, every filter, limit clamp, candidate
  lists, twin copies, the Windows gate), and the `register(ctx)` wiring.
- Live layer, this machine: the user Root store walks with complete rows
  (46 certificates — `Get-ChildItem Cert:\CurrentUser\Root` answers 46 too),
  the machine Root store as well (46 = 46), self-signed roots are present, the
  full default walk (2 contexts x 3 stores) reads **121 certificates in 8 ms**,
  and the machine's intermediate CA store answers unelevated.

## Cross-checks against the system's own view

- Store counts agree with the PowerShell certificate provider exactly:
  user Root 46/46, machine Root 46/46.
- A sampled certificate agrees field by field:
  `Microsoft Root Certificate Authority`, until `2021-05-10T07:28:13+08:00`
  (PS shows 05/10/2021 07:28:13), thumbprint `CDD4EEAE6000AC7F…` identical,
  self-signed true, signature OID `1.2.840.113549.1.1.5`
  (sha1WithRSAEncryption — a 2011-era root, correctly expired on this machine).
- The simple-display name form is shorter than PS's full DN (`CN=…, DC=…`) by
  design: it is the name Windows itself shows in the certificate dialogs.

## Real-machine findings the tools surface

- 20 of 121 certificates on this machine are expired, expiring within 30 days,
  or not valid yet; `expired_only=true` lists them.
- 96 self-signed certificates (the roots) — counted in the notes so a healthy
  root store is not misread as 96 problems.

## API decisions worth recording

- `CertOpenStore` and `CertGetCertificateContextProperty` have no W-suffixed
  exports (verified by probing the DLL: `CertOpenStoreW` /
  `CertGetCertificateContextPropertyW` do not exist); `CertGetNameStringW` does.
  `CertOpenStore` takes the provider constant 10 as a pointer-sized integer and
  the store name wide for it.
- `CertEnumCertificatesInStore` frees the previous context itself, including on
  the NULL-returning call that ends the walk; facts are copied out before the
  next step because the context dies with it.
- `CertGetEnhancedKeyUsage` answers `CRYPT_E_NOT_FOUND` for a certificate with
  no EKU extension — that is the "valid for any purpose" answer, reported as
  such, not an error.
- RSA key size comes from a minimal DER walk of the public-key blob (SEQUENCE
  of two INTEGERs), long and short length forms; a leading 00 sign byte is not
  a key bit. Named curves are matched by OID content bytes inside the
  algorithm parameters, so no ASN.1 parser is needed for either.

## Admission

- Working copy: `validate_plugin_dir` 15/15 PASS, zero warnings, security scan
  safe.
- Pinned tarball: same 15/15 PASS, zero warnings, safe (see the entry PR).
