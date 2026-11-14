import pytest

from app.core.csv import safe
from app.core.ratelimit import MemoryLimiter, RedisLimiter
from app.core.security import (csrf_token_for, hash_password, password_problem, verify_password)
from app.core.utils import new_request_code, normalize_phone
from app.modules.requests.service import parse_day


@pytest.mark.parametrize("raw,expected", [("0712 345 678", "254712345678"), ("+254 712-345-678", "254712345678"),
                                          ("712345678", "254712345678"), ("0112345678", "254112345678"),
                                          ("+254712345678", "254712345678"), ("254712345678", "254712345678"),
                                          ("+254 0712 345 678", "254712345678")])
def test_phone_normalised(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["", "123", "0812345678", "abcdefghij", "07123456789"])
def test_bad_phone_rejected(raw):
    with pytest.raises(ValueError):
        normalize_phone(raw)


def test_request_code_format():
    assert all(len(c := new_request_code()) == 9 and c.startswith("MM-") for _ in range(50))


def test_passwords_use_argon2id():
    h = hash_password("a-long-password")
    assert h.startswith("$argon2id$") and verify_password(h, "a-long-password") and not verify_password(h, "wrong")
    assert not verify_password("not-a-hash", "x")


def test_password_rules():
    assert password_problem("short") and password_problem("x" * 201) and password_problem("long-enough-1") is None


def test_csrf_token_is_per_session_and_stable():
    assert csrf_token_for("a") == csrf_token_for("a") != csrf_token_for("b")


def test_csv_neutralises_formulas():
    assert safe("=1+1") == "'=1+1" and safe("@x") == "'@x" and safe("-5") == "'-5" and safe("normal") == "normal" and safe(None) == ""


def test_parse_day():
    assert parse_day("2026-11-10").utcoffset().total_seconds() == 3 * 3600 and parse_day("nope") is None
    assert (parse_day("2026-11-10", end=True) - parse_day("2026-11-10")).days == 1


def test_memory_limiter_blocks_and_resets():
    lim = MemoryLimiter("t", 3, 60)
    for _ in range(3):
        assert not lim.blocked("k")
        lim.fail("k")
    assert lim.blocked("k") and not lim.blocked("other")
    lim.reset("k")
    assert not lim.blocked("k")


def test_redis_limiter_blocks_and_is_shared_across_instances():
    import fakeredis
    r = fakeredis.FakeRedis()
    a, b = RedisLimiter(r, "t", 3, 60), RedisLimiter(r, "t", 3, 60)  # two "workers"
    for _ in range(3):
        a.fail("k")
    assert b.blocked("k") and b.retry_minutes("k") >= 1
    b.reset("k")
    assert not a.blocked("k")


def test_redis_limiter_falls_back_when_redis_is_down():
    class Down:
        def __getattr__(self, name):
            raise ConnectionError("down")
    lim = RedisLimiter(Down(), "t", 2, 60)
    lim.fail("k"); lim.fail("k")
    assert lim.blocked("k")  # still limited, from the in-memory fallback


def test_production_refuses_weak_settings(monkeypatch):
    from app.core import config
    monkeypatch.setattr(config.settings, "app_env", "production")
    monkeypatch.setattr(config.settings, "secret_key", config.DEFAULT_SECRET)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        config.check_production_settings()
