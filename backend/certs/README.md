# Public Supabase database CA

`supabase-root.crt` is a public trust anchor, not a private key or credential.

- Downloaded over verified HTTPS on 2026-10-19 from:
  https://supabase-downloads.s3-ap-southeast-1.amazonaws.com/prod/ssl/prod-ca-2021.crt
- Subject: Supabase Inc / Supabase Root 2021 CA
- Expires: 2031-04-26 10:56:53 GMT
- File SHA-256: `700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7`

The database connection helper loads this CA only for Supabase hostnames, in
addition to system CAs, while retaining certificate and hostname verification.
For Python 3.13 compatibility it disables only the X509_STRICT flag on these
connections: the current Supabase intermediate lacks the Key Usage extension.
Other PostgreSQL hosts retain the system's default verification flags.

See https://supabase.com/docs/guides/platform/ssl-enforcement and
https://github.com/supabase/supabase/issues/50862. Update this bundle when Supabase
rotates its database CA; do not replace it with an unverified server certificate.
