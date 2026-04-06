import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestDashboard:
    def test_dashboard_stats(self):
        r = requests.get(f"{BASE_URL}/api/dashboard/stats")
        assert r.status_code == 200
        data = r.json()
        assert "total_leads" in data
        assert "high_priority" in data
        assert "new_this_week" in data
        assert "conversion_rate" in data
        assert "city_distribution" in data
        assert "segment_distribution" in data
        assert "recent_leads" in data
        assert "top_leads" in data
        assert data["total_leads"] > 0
        print(f"Total leads: {data['total_leads']}, High priority: {data['high_priority']}")

class TestLeads:
    def test_get_leads(self):
        r = requests.get(f"{BASE_URL}/api/leads")
        assert r.status_code == 200
        data = r.json()
        assert "leads" in data
        assert "total" in data
        assert data["total"] > 0
        print(f"Total leads: {data['total']}")

    def test_get_leads_search(self):
        r = requests.get(f"{BASE_URL}/api/leads?search=Mumbai")
        assert r.status_code == 200
        data = r.json()
        assert "leads" in data

    def test_get_leads_filter_segment(self):
        r = requests.get(f"{BASE_URL}/api/leads?segment=Hotel")
        assert r.status_code == 200
        data = r.json()
        assert all(l["segment"] == "Hotel" for l in data["leads"])

    def test_get_leads_filter_priority(self):
        r = requests.get(f"{BASE_URL}/api/leads?priority=High")
        assert r.status_code == 200

    def test_create_lead(self):
        payload = {
            "business_name": "TEST_Lead Automation",
            "segment": "Bakery",
            "city": "Mumbai",
            "state": "Maharashtra",
            "tier": 1,
            "rating": 4.5,
            "num_outlets": 5,
            "has_dessert_menu": True,
            "is_chain": True
        }
        r = requests.post(f"{BASE_URL}/api/leads", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["business_name"] == "TEST_Lead Automation"
        assert "ai_score" in data
        assert "priority" in data
        assert "id" in data
        self.__class__.created_lead_id = data["id"]
        print(f"Created lead with score: {data['ai_score']}, priority: {data['priority']}")

    def test_get_lead_by_id(self):
        # Get a lead first
        r = requests.get(f"{BASE_URL}/api/leads?limit=1")
        lead_id = r.json()["leads"][0]["id"]
        r2 = requests.get(f"{BASE_URL}/api/leads/{lead_id}")
        assert r2.status_code == 200
        assert r2.json()["id"] == lead_id

    def test_get_lead_not_found(self):
        r = requests.get(f"{BASE_URL}/api/leads/nonexistent-id")
        assert r.status_code == 404

    def test_update_lead_status(self):
        r = requests.get(f"{BASE_URL}/api/leads?limit=1")
        lead_id = r.json()["leads"][0]["id"]
        r2 = requests.put(f"{BASE_URL}/api/leads/{lead_id}/status", json={"status": "contacted"})
        assert r2.status_code == 200
        assert r2.json()["status"] == "contacted"

    def test_csv_template_download(self):
        r = requests.get(f"{BASE_URL}/api/leads/csv-template")
        assert r.status_code == 200
        assert "business_name" in r.text
        assert "segment" in r.text

class TestDiscover:
    def test_discover_leads(self):
        r = requests.post(f"{BASE_URL}/api/leads/discover", json={"city": "Mumbai", "segment": "Bakery"})
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert data[0]["city"] == "Mumbai"
        assert data[0]["segment"] == "Bakery"
        print(f"Discovered {len(data)} leads")

    def test_bulk_create_leads(self):
        r = requests.post(f"{BASE_URL}/api/leads/discover", json={"city": "Delhi", "segment": "Cafe"})
        discovered = r.json()
        bulk_r = requests.post(f"{BASE_URL}/api/leads/bulk-create", json={"leads": discovered[:2]})
        assert bulk_r.status_code == 200
        data = bulk_r.json()
        assert data["created"] == 2

class TestOutreach:
    def test_get_all_emails(self):
        r = requests.get(f"{BASE_URL}/api/outreach/emails")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_get_lead_emails(self):
        r = requests.get(f"{BASE_URL}/api/leads?limit=1")
        lead_id = r.json()["leads"][0]["id"]
        r2 = requests.get(f"{BASE_URL}/api/outreach/{lead_id}/emails")
        assert r2.status_code == 200
        assert isinstance(r2.json(), list)

class TestAI:
    def test_generate_email(self):
        r = requests.get(f"{BASE_URL}/api/leads?limit=1")
        lead_id = r.json()["leads"][0]["id"]
        r2 = requests.post(f"{BASE_URL}/api/leads/{lead_id}/generate-email", timeout=30)
        assert r2.status_code == 200
        data = r2.json()
        assert "subject" in data
        assert "body" in data
        assert len(data["subject"]) > 0
        print(f"Generated email with subject: {data['subject'][:50]}")

    def test_qualify_ai(self):
        r = requests.get(f"{BASE_URL}/api/leads?limit=1")
        lead_id = r.json()["leads"][0]["id"]
        r2 = requests.post(f"{BASE_URL}/api/leads/{lead_id}/qualify-ai", timeout=30)
        assert r2.status_code == 200
        data = r2.json()
        assert "lead" in data
        assert "ai_analysis" in data
        print(f"AI score: {data['ai_analysis'].get('ai_score')}")
