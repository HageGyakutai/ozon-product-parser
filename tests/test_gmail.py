from ozon_parser.gmail import verification_code


def test_code():
    assert verification_code("Ваш код: 123456") == "123456"
    assert verification_code("No verification here") is None
