# secure_mqtt_broker/broker/tls.py

import ssl

def create_tls_context(
    certfile: str,
    keyfile: str,
    cafile: str = None,
    require_client_cert: bool = False
) -> ssl.SSLContext:
    """
    Build and return an SSLContext for MQTT-over-TLS.

    :param certfile: path to the broker's server certificate (.crt)
    :param keyfile:  path to the broker's private key (.key)
    :param cafile:   optional CA bundle to verify client certs
    :param require_client_cert: if True, enforce client cert verification
    """
    # Create a context that will verify clients if requested
    ctx = ssl.create_default_context(
        purpose=ssl.Purpose.CLIENT_AUTH,
        cafile=cafile
    )

    # Load our server cert and key
    ctx.load_cert_chain(certfile=certfile, keyfile=keyfile)

    # If mutual‑TLS is on, require clients to present a valid certificate
    if require_client_cert:
        ctx.verify_mode = ssl.CERT_REQUIRED

    return ctx
