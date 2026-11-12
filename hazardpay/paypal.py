"""PayPal (sandbox): the premium is a checkout, the claim is a payout.

  premium  Orders v2: create (CAPTURE intent, PayPal-Request-Id idempotent) -> buyer approves -> capture
  claim    Payouts v1: one sync payout item to the robot operator's PayPal email, with the claim id
  events   webhooks, verified with verify-webhook-signature when PAYPAL_WEBHOOK_ID is set

Without keys everything runs against an offline fake, and the UI says DEMO.
"""
import os
import time
import uuid

import httpx

CID = os.getenv("PAYPAL_CLIENT_ID", "").strip()
SECRET = os.getenv("PAYPAL_CLIENT_SECRET", "").strip()
BASE = os.getenv("PAYPAL_BASE", "https://api-m.sandbox.paypal.com")
WEBHOOK_ID = os.getenv("PAYPAL_WEBHOOK_ID", "").strip()
_tok = {"v": None, "exp": 0.0}
FAKE: dict[str, dict] = {}


def live() -> bool:
    return bool(CID and SECRET) and os.getenv("DEMO_MODE", "").lower() not in {"1", "true", "yes"}


def _auth() -> str:
    if _tok["v"] and time.time() < _tok["exp"] - 60:
        return _tok["v"]
    r = httpx.post(f"{BASE}/v1/oauth2/token", auth=(CID, SECRET), data={"grant_type": "client_credentials"}, timeout=20)
    r.raise_for_status()
    j = r.json()
    _tok.update(v=j["access_token"], exp=time.time() + int(j.get("expires_in", 3000)))
    return _tok["v"]


def _h(extra=None):
    return {"Authorization": f"Bearer {_auth()}", "Content-Type": "application/json", **(extra or {})}


def create_premium_order(policy: dict, return_url: str, cancel_url: str) -> dict:
    body = {"intent": "CAPTURE", "purchase_units": [{
        "reference_id": policy["signature"][:20], "custom_id": policy["mission_hash"],
        "description": f"Hazard Pay mission cover: {policy['mission'][:60]} (P(fail) {policy['p_fail'] * 100:.1f}%)",
        "amount": {"currency_code": "USD", "value": f"{policy['premium']:.2f}"}}],
        "payment_source": {"paypal": {"experience_context": {
            "brand_name": "Hazard Pay", "user_action": "PAY_NOW", "shipping_preference": "NO_SHIPPING",
            "return_url": return_url, "cancel_url": cancel_url}}}}
    if not live():
        oid = "FAKE-" + uuid.uuid4().hex[:12].upper()
        FAKE[oid] = {"status": "CREATED", "body": body}
        return {"id": oid, "status": "CREATED", "mode": "DEMO", "approve_url": f"{return_url}?token={oid}"}
    r = httpx.post(f"{BASE}/v2/checkout/orders", json=body, timeout=30,
                   headers=_h({"PayPal-Request-Id": "prem-" + policy["signature"][:24], "Prefer": "return=representation"}))
    if r.status_code >= 300:
        raise RuntimeError(f"PayPal {r.status_code}: {r.text[:400]}")
    j = r.json()
    link = next((l["href"] for l in j.get("links", []) if l.get("rel") in {"payer-action", "approve"}), None)
    return {"id": j["id"], "status": j["status"], "mode": "SANDBOX", "approve_url": link}


def get_order(order_id: str) -> dict:
    if not live():
        return {"id": order_id, "status": "APPROVED", "mode": "DEMO"}
    r = httpx.get(f"{BASE}/v2/checkout/orders/{order_id}", headers=_h(), timeout=20)
    r.raise_for_status()
    return {"id": order_id, "status": r.json().get("status"), "mode": "SANDBOX"}


TEST_CARD = {"number": "4111111111111111", "expiry": "2030-12", "security_code": "123", "name": "Sandbox Tester",
             "billing_address": {"address_line_1": "1 Main St", "admin_area_2": "San Jose", "admin_area_1": "CA",
                                 "postal_code": "95131", "country_code": "US"}}


def pay_premium_server_side(policy: dict) -> dict:
    """Sandbox only: create AND capture the premium order in one call with PayPal's published test card,
    so a demo needs no buyer login. Requires Advanced Card Processing on the sandbox app."""
    body = {"intent": "CAPTURE", "purchase_units": [{
        "reference_id": policy["signature"][:20], "custom_id": policy["mission_hash"],
        "description": f"Hazard Pay mission cover: {policy['mission'][:60]}",
        "amount": {"currency_code": "USD", "value": f"{policy['premium']:.2f}"}}],
        "payment_source": {"card": TEST_CARD}}
    if not live():
        oid = "FAKE-" + uuid.uuid4().hex[:12].upper()
        return {"id": oid, "status": "COMPLETED", "mode": "DEMO", "capture_id": "FAKECAP-" + oid[-6:], "approve_url": None}
    if "sandbox" not in BASE:
        raise RuntimeError("server-side test card is sandbox only")
    r = httpx.post(f"{BASE}/v2/checkout/orders", json=body, timeout=40,
                   headers=_h({"PayPal-Request-Id": "prem-card-" + policy["signature"][:20], "Prefer": "return=representation"}))
    if r.status_code >= 300:
        raise RuntimeError(f"PayPal {r.status_code}: {r.text[:400]}")
    j = r.json()
    cap = (((j.get("purchase_units") or [{}])[0].get("payments") or {}).get("captures") or [{}])[0]
    return {"id": j["id"], "status": j.get("status"), "mode": "SANDBOX (test card)", "capture_id": cap.get("id"), "approve_url": None}


def capture(order_id: str) -> dict:
    if not live():
        FAKE.setdefault(order_id, {})["status"] = "COMPLETED"
        return {"id": order_id, "status": "COMPLETED", "mode": "DEMO", "capture_id": "FAKECAP-" + order_id[-6:]}
    r = httpx.post(f"{BASE}/v2/checkout/orders/{order_id}/capture", json={}, timeout=30,
                   headers=_h({"PayPal-Request-Id": "cap-" + order_id}))
    if r.status_code >= 300:
        raise RuntimeError(f"PayPal {r.status_code}: {r.text[:400]}")
    j = r.json()
    cap = (((j.get("purchase_units") or [{}])[0].get("payments") or {}).get("captures") or [{}])[0]
    return {"id": order_id, "status": j.get("status"), "mode": "SANDBOX", "capture_id": cap.get("id")}


def payout(claim_id: str, receiver_email: str, amount: float, note: str) -> dict:
    body = {"sender_batch_header": {"sender_batch_id": "claim-" + claim_id, "email_subject": "Hazard Pay claim paid",
                                    "email_message": note[:255]},
            "items": [{"recipient_type": "EMAIL", "receiver": receiver_email, "sender_item_id": claim_id,
                       "amount": {"currency": "USD", "value": f"{amount:.2f}"}, "note": note[:4000]}]}
    if not live():
        bid = "FAKEBATCH-" + uuid.uuid4().hex[:10].upper()
        return {"batch_id": bid, "status": "SUCCESS", "mode": "DEMO"}
    r = httpx.post(f"{BASE}/v1/payments/payouts", json=body, timeout=30, headers=_h())
    if r.status_code >= 300:
        raise RuntimeError(f"PayPal {r.status_code}: {r.text[:400]}")
    j = r.json()
    return {"batch_id": j["batch_header"]["payout_batch_id"], "status": j["batch_header"]["batch_status"], "mode": "SANDBOX"}


def payout_status(batch_id: str) -> dict:
    if not live():
        return {"batch_id": batch_id, "status": "SUCCESS", "mode": "DEMO"}
    r = httpx.get(f"{BASE}/v1/payments/payouts/{batch_id}", headers=_h(), timeout=20)
    r.raise_for_status()
    return {"batch_id": batch_id, "status": r.json()["batch_header"]["batch_status"], "mode": "SANDBOX"}


def verify_webhook(headers: dict, event: dict):
    if not (live() and WEBHOOK_ID):
        return None
    h = {k.lower(): v for k, v in headers.items()}
    body = {"auth_algo": h.get("paypal-auth-algo"), "cert_url": h.get("paypal-cert-url"),
            "transmission_id": h.get("paypal-transmission-id"), "transmission_sig": h.get("paypal-transmission-sig"),
            "transmission_time": h.get("paypal-transmission-time"), "webhook_id": WEBHOOK_ID, "webhook_event": event}
    try:
        r = httpx.post(f"{BASE}/v1/notifications/verify-webhook-signature", json=body, headers=_h(), timeout=20)
        return r.json().get("verification_status") == "SUCCESS"
    except Exception:
        return None
