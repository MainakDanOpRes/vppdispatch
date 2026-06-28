
from fastapi.testclient import TestClient
from vpp_dispatch.api import app

client = TestClient(app)

def test_dispatch_single():
    payload = {
        "customer_id": "C1",
        "pv_kw": [0,0,1,3,5,4,2,0,0,0,0,0],
        "fixed_load_kw": [1,1,1,1,1,1,1,1,1,1,1,1],
        "price_buy": [0.2]*12,
        "price_sell": [0.1]*12,
    }
    r = client.post("/dispatch", json=payload)
    assert r.status_code == 200
    result = r.json()
    # power balance holds
    for t in range(12):
        lhs = payload["pv_kw"][t] + result["p_grid"][t]
        rhs = payload["fixed_load_kw"][t] + result["flex_ev"][t] + result["p_ch"][t] - result["p_dis"][t]
        assert abs(lhs - rhs) < 1e-4
