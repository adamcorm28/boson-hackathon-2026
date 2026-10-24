"""The real Higgs Realtime connection used by CallSession."""

import websockets


async def connect_boson():
    # Imported lazily: main imports the gateway, and main needs BOSON_API_KEY at import.
    from main import AUTH_HEADERS, REALTIME_URL, SSL_CONTEXT

    # A websockets connection already satisfies the Upstream protocol (send, async iter, close).
    return await websockets.connect(REALTIME_URL, additional_headers=AUTH_HEADERS, ssl=SSL_CONTEXT, max_size=None)
