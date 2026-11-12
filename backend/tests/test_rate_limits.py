from app import _consume_rate_limit, _rate_limit_policy, _RATE_LIMIT_BUCKETS


def setup_function():
    _RATE_LIMIT_BUCKETS.clear()


def test_auth_registration_and_upload_routes_have_rate_limits():
    assert _rate_limit_policy("POST", "/auth/login") == ("login", 5, 60)
    assert _rate_limit_policy("POST", "/auth/register") == ("registration", 10, 60)
    assert _rate_limit_policy("POST", "/auth/registrations/123/receipt") == ("receipt-upload", 5, 60)
    assert _rate_limit_policy("POST", "/auth/reconciliation/statement") == ("statement-upload", 5, 60)


def test_sensitive_network_and_card_mutations_have_rate_limits():
    assert _rate_limit_policy("POST", "/mikrotik/reboot") == ("router-reboot", 3, 60)
    assert _rate_limit_policy("POST", "/cards/generate") == ("card-generation", 10, 60)
    assert _rate_limit_policy("GET", "/auth/login") is None


def test_rate_limiter_blocks_excess_calls_and_recovers_after_window():
    for attempt in range(5):
        assert _consume_rate_limit("198.51.100.10", "login", 5, 60, now=float(attempt)) is None
    retry_after = _consume_rate_limit("198.51.100.10", "login", 5, 60, now=5.0)
    assert retry_after == 55
    assert _consume_rate_limit("198.51.100.10", "login", 5, 60, now=60.0) is None
