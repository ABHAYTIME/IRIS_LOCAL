import requests

# Let's see what /api/operator/override does
res = requests.post("http://localhost:5000/api/operator/override", json={
    "incident_id": 1,
    "ambulance_id": 1
})
print("Status Code:", res.status_code)
print("Response text:", res.text)
