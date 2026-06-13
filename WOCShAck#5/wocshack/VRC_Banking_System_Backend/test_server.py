import unittest

from socket_policy import ALLOWED_CLIENT_IP, is_allowed_client_ip


class AllowedClientIPTests(unittest.TestCase):
    def test_allowed_client_ip_matches_django_container(self):
        self.assertEqual(ALLOWED_CLIENT_IP, "172.28.0.3")

    def test_only_the_allowed_client_ip_is_accepted(self):
        self.assertTrue(is_allowed_client_ip("172.28.0.3"))
        self.assertFalse(is_allowed_client_ip("172.28.0.4"))


if __name__ == "__main__":
    unittest.main()
