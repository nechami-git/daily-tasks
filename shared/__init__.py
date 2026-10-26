"""Shared domain code (tools + data) used by both API/ and SDK/."""
import truststore

# Behind an HTTPS-inspecting filter (e.g. Rimon) the TLS chain ends in a local root CA
# that only the OS store knows. This makes every Python TLS client in the process
# (requests for Hebcal, the anthropic client) verify against the OS store.
# Must run before any HTTPS client is created; importing `shared` does it.
truststore.inject_into_ssl()
