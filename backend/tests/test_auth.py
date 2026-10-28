def test_development_operator_login(client):
    config = client.get("/api/auth/config").json()
    assert config["key_required"] is False
    assert config["password_auth_enabled"] is True
    assert config["registration_enabled"] is True
    assert config["development_open_access"] is False
    response = client.post("/api/auth/login", json={"name": "Hemanth", "key": ""})
    assert response.status_code == 200
    assert response.json() == {"authenticated": True, "name": "Hemanth", "mode": "development"}


def test_operator_login_requires_configured_shared_key(client, cfg):
    cfg(operator_api_key="test-secret")
    assert client.get("/api/auth/config").json()["key_required"] is True
    assert client.post("/api/auth/login", json={"name": "Hemanth", "key": "wrong"}).status_code == 401
    response = client.post("/api/auth/login", json={"name": "Hemanth", "key": "test-secret"})
    assert response.status_code == 200
    assert response.json()["mode"] == "shared_key"


def test_production_requires_an_operator_key(client, cfg):
    cfg(app_env="production", operator_api_key="")
    response = client.post("/api/auth/login", json={"name": "Hemanth", "key": ""})
    assert response.status_code == 503


def test_operator_login_validates_name_and_body(client):
    assert client.post("/api/auth/login", json={"name": " ", "key": ""}).status_code == 422
    assert client.post("/api/auth/login", json={"name": "H", "key": ""}).status_code == 422
