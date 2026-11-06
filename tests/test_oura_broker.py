"""Offline fake-HTTP broker sender, no Bluetooth or microphone."""
from test_oura_gestures import oura
import json
import pytest

def test_broker_contract_and_no_dual_dispatch(tmp_path):
    token = tmp_path / "token"; token.write_text("synthetic-test-token"); token.chmod(0o600)
    calls = []
    class Response:
        def __init__(self, request): self.request = request
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def geturl(self): return self.request.full_url
        def read(self, size):
            return json.dumps({"device_id":"a"*32} if self.request.full_url.endswith("/self") else {"ok":True}).encode()
    def opener(request,**kwargs):
        calls.append(request); assert kwargs["timeout"] == 1.0; return Response(request)
    fallback = oura.ActionRouter({"double_tap":["must-not-run"]},runner=lambda *a,**k:pytest.fail("dual dispatch"))
    r = oura.BrokerRouter("https://broker.example", token, opener=opener, fallback=fallback)
    r.claim(120); r.dispatch("double_tap"); r.dispatch("triple_tap"); r.release()
    assert [c.full_url.rsplit("/",1)[-1] for c in calls] == ["self","listener","gesture","gesture","listener"]
    event = json.loads(calls[2].data)
    assert set(event) == {"gesture","source_device","ts","nonce"}
    assert event["source_device"] == "a"*32
    assert json.loads(calls[-1].data)["enabled"] is False

def test_expired_lease_and_private_file(tmp_path,capsys):
    token = tmp_path / "token"; token.write_text("synthetic"); token.chmod(0o644)
    with pytest.raises(ValueError): oura.BrokerRouter("https://broker.example",token)
    r=oura.BrokerRouter("https://broker.example",None,dry_run=True)
    r.dry_run=False;r.dispatch("double_tap")
    assert "expired" in capsys.readouterr().err

@pytest.mark.parametrize("url",["http://broker.example","https://user:pass@broker.example","https://broker.example/path","https://broker.example?x=1"])
def test_origin_validation(url):
    with pytest.raises(ValueError): oura.BrokerRouter(url,None,dry_run=True)

def test_bounded_acm():
    assert len(oura.realtime_start(300)) == 9
    with pytest.raises(ValueError): oura.realtime_start(301)
