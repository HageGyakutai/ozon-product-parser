from ozon_parser.auth_guard import blocked_page_text


def test_ozon_access_denied_page():
    assert blocked_page_text("Похоже, нет соединения. Выключите VPN. Обратиться в поддержку")


def test_login_page_is_not_blocked():
    assert not blocked_page_text("Введите номер телефона. Войти")
