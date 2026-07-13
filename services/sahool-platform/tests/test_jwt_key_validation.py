import pytest
from shared.security.jwt_key_validation import (
    looks_like_placeholder,
    validate_rsa_key_pair,
    validate_rsa_public_key_pem,
)


def test_placeholder_public_key_is_rejected():
    with pytest.raises(ValueError, match="placeholder"):
        validate_rsa_public_key_pem("aasdasdasdasdasdad")


def test_non_pem_public_key_is_rejected():
    with pytest.raises(ValueError, match="PEM"):
        validate_rsa_public_key_pem("not-a-key")


def test_empty_public_key_keeps_explicit_dev_fallback():
    assert validate_rsa_public_key_pem("") == ""


def test_placeholder_detector():
    assert looks_like_placeholder("CHANGE-ME")
    assert not looks_like_placeholder("")



def test_rejects_partial_rsa_pair():
    import pytest
    with pytest.raises(ValueError, match="configured together"):
        validate_rsa_key_pair("", "-----BEGIN PUBLIC KEY-----\ninvalid\n-----END PUBLIC KEY-----")
