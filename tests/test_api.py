from fastapi.testclient import TestClient
from studio.server import app

def test_local_api_and_mutation_protection():
    client=TestClient(app)
    assert client.get('/api/health').json()['ok']
    assert client.post('/api/render',json={}).status_code==403
    token=client.get('/api/state').json()['token']
    assert client.post('/api/render',headers={'x-studio-token':token},json={}).status_code==422
    assert client.get('/api/tracks/not-a-track/audio').status_code==404
    assert client.get('/api/exports/abcd/secret.txt').status_code==404
    assert client.get('/api/health',headers={'host':'attacker.example'}).status_code==400
