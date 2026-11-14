from sqlalchemy import select

from app.modules.customers.models import Customer
from app.modules.notifications.models import Notification
from app.modules.requests.models import RequestStatusHistory, ServiceRequest
from tests.conftest import make_request


def test_home_lists_services_by_category(client):
    html = client.get("/").text
    assert client.get("/").status_code == 200 and "HELB Scholarship" in html and "KSh 1,000" in html and "Ask for quote" in html
    assert html.count("Passport applications") >= 2  # services list and its category box


def test_request_creates_customer_history_notification_and_price_snapshot(client, db):
    r = client.post("/request", data={"service": "ntsa", "name": "Amina Hassan", "phone": "0722 111 222", "details": "Renew licence"})
    assert r.status_code == 303 and r.headers["location"].startswith("/track/MM-")
    req = db.scalar(select(ServiceRequest))
    assert req.fee == 600 and req.service_name == "NTSA" and req.customer.phone == "254722111222" and req.status == "received"
    assert [h.to_status for h in db.scalars(select(RequestStatusHistory))] == ["received"]
    assert db.scalar(select(Notification)).message.startswith("New request MM-")


def test_same_phone_reuses_the_customer(client, db):
    make_request(db, name="Amina"); make_request(db, name="Amina Hassan", slug="tsc")
    customers = db.scalars(select(Customer)).all()
    assert len(customers) == 1 and customers[0].name == "Amina Hassan" and len(db.scalars(select(ServiceRequest)).all()) == 2


def test_invalid_requests_are_rejected_without_saving(client, db):
    assert client.post("/request", data={"service": "ntsa", "name": "A", "phone": "0712345678"}).status_code == 422
    assert client.post("/request", data={"service": "ntsa", "name": "Jane", "phone": "123"}).status_code == 422
    assert client.post("/request", data={"service": "nope", "name": "Jane", "phone": "0712345678"}).status_code == 422
    assert db.scalar(select(ServiceRequest)) is None


def test_honeypot_drops_bots_silently(client, db):
    r = client.post("/request", data={"service": "ntsa", "name": "Bot", "phone": "0712345678", "website": "http://spam"})
    assert r.status_code == 303 and r.headers["location"] == "/" and db.scalar(select(ServiceRequest)) is None


def test_tracking_page_and_unknown_code(client, db, req):
    page = client.get(f"/track/{req.code}")
    assert page.status_code == 200 and req.code in page.text and "New" in page.text
    assert client.get("/track/MM-NOPE00").status_code == 404
    assert client.get(f"/track?code={req.code.lower()}").headers["location"] == f"/track/{req.code}"


def test_public_api(client, db):
    services = client.get("/api/services").json()
    assert {"slug": "kra-itax", "name": "KRA", "description": "Help with KRA online services.",
            "categories": ["government"], "price": 200} in services
    made = client.post("/api/requests", json={"service": "tsc", "name": "Bob Otieno", "phone": "0700111222"})
    assert made.status_code == 201
    code = made.json()["code"]
    assert client.get(f"/api/track/{code}").json()["status"] == "received"
    assert client.get("/api/track/MM-000000").status_code == 404
    assert client.post("/api/requests", json={"service": "tsc", "name": "B", "phone": "x"}).status_code == 422


def test_health_endpoints(client):
    assert client.get("/health").json() == {"ok": True} and client.get("/health/ready").json()["database"] == "up"


def test_docs_are_off_outside_debug(client):
    assert client.get("/docs").status_code == 404 and client.get("/openapi.json").status_code == 404


def test_navbar_has_the_five_links_and_admin_login(client):
    html = client.get("/").text
    for label in ("Home", "Services", "Track Request", "About", "Contact", "Admin Login"):
        assert label in html
    assert 'href="/admin/login"' in html and "MENDEX CLOUD SOFTS" in html and "Iammendexmendle" not in html


def test_about_and_contact_pages_use_configured_details(client):
    assert client.get("/about").status_code == 200
    page = client.get("/contact").text
    assert "0708 337 199" in page and "mendexbackup072@gmail.com" in page and "wa.me/254708337199" in page
    assert 'aria-current="page"' in page


def test_contact_form_saves_an_alert_for_the_team(client, db):
    from sqlalchemy import select
    from app.modules.notifications.models import Notification
    r = client.post("/contact", data={"name": "Amina", "contact": "0712345678", "message": "Do you help with passports?"})
    assert r.status_code == 303 and r.headers["location"] == "/contact?sent=1"
    note = db.scalar(select(Notification).where(Notification.kind == "contact"))
    assert note and "Amina" in note.message and "passports" in note.message
    assert "Thank you" in client.get("/contact?sent=1").text


def test_contact_form_rejects_bad_input_and_honeypot(client, db):
    from sqlalchemy import select
    from app.modules.notifications.models import Notification
    assert client.post("/contact", data={"name": "A", "contact": "x", "message": "hello there"}).status_code == 422
    assert client.post("/contact", data={"name": "Amina", "contact": "", "message": "hello there"}).status_code == 422
    assert client.post("/contact", data={"name": "Amina", "contact": "x", "message": "hi"}).status_code == 422
    client.post("/contact", data={"name": "Bot", "contact": "x", "message": "spam spam", "website": "http://x"})
    assert db.scalar(select(Notification).where(Notification.kind == "contact")) is None


def test_services_page_lists_prices_and_links_from_the_navbar(client):
    page = client.get("/services")
    assert page.status_code == 200
    assert "Government services" in page.text and "Education services" in page.text and "Online services" in page.text and "KSh" in page.text
    assert 'href="/services#government"' in client.get("/").text


def test_tracking_page_helps_customers_keep_their_code(client, db):
    from tests.conftest import make_request
    r = make_request(db)
    page = client.get(f"/track/{r.code}?new=1").text
    assert r.code in page and "Copy code" in page and "Save code on WhatsApp" in page and "https://wa.me/?text=" in page
    assert r.customer.phone not in page  # the customer's number is never put on the public page
    assert "Lost it?" in client.get("/track").text


def test_admin_can_send_the_tracking_code_on_whatsapp(admin, db):
    from tests.conftest import make_request
    r = make_request(db)
    html = admin.get(f"/admin/requests/{r.id}").text
    assert "Send tracking code on WhatsApp" in html and f"wa.me/{r.customer.phone}" in html and r.code in html
