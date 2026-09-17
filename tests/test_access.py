import unittest

from app.access import Transport, classify_transport
from app.config import Settings


class AccessPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings.for_test(__import__("pathlib").Path("/tmp/nmixx-radar-access-test"))

    def test_public_http_peer_cannot_receive_lan_transport(self) -> None:
        transport = classify_transport("8.8.8.8", "http", None, self.settings)
        self.assertEqual(transport, Transport.PUBLIC_HTTP)

    def test_private_http_peer_uses_lan_transport_when_enabled(self) -> None:
        transport = classify_transport("192.168.1.10", "http", None, self.settings)
        self.assertEqual(transport, Transport.LAN_HTTP)

    def test_trusted_proxy_can_mark_request_as_https(self) -> None:
        transport = classify_transport("127.0.0.1", "http", "https", self.settings)
        self.assertEqual(transport, Transport.HTTPS)

    def test_untrusted_peer_cannot_spoof_forwarded_https_header(self) -> None:
        transport = classify_transport("8.8.8.8", "http", "https", self.settings)
        self.assertEqual(transport, Transport.PUBLIC_HTTP)


if __name__ == "__main__":
    unittest.main()
