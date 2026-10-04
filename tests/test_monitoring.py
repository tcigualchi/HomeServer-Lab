from backend.app.monitoring import server_status

def test_server_status_has_real_metrics():
    status = server_status()
    assert status["hostname"]
    assert 0 <= status["cpu_percent"] <= 100
    assert 0 <= status["memory_percent"] <= 100
    assert 0 <= status["disk_percent"] <= 100
