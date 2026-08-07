import os
import httpx

CALCOM_API_URL = "https://api.cal.com/v2"
CALCOM_API_KEY = os.getenv("CALCOM_API_KEY")
EVENT_TYPE_ID = os.getenv("EVENT_TYPE_ID")

async def check_availability(date: str, time: str):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{CALCOM_API_URL}/slots",
            params={"eventTypeId": EVENT_TYPE_ID, "date": date},
            headers={"Authorization": f"Bearer {CALCOM_API_KEY}"}
        )
        response.raise_for_status()
        return response.json()

async def create_booking(name: str, email: str, date: str, time: str):
    payload = {
        "eventTypeId": EVENT_TYPE_ID,
        "start": f"{date}T{time}:00Z",
        "attendees": [{"name": name, "email": email}],
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{CALCOM_API_URL}/bookings",
            json=payload,
            headers={"Authorization": f"Bearer {CALCOM_API_KEY}"}
        )
        response.raise_for_status()
        return response.json()
