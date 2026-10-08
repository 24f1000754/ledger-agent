import requests

URL = "http://127.0.0.1:5000/answer"
# Render pe test karna ho to:
# URL = "https://ledger-agent-3pjf.onrender.com/answer"

questions = [
    "What was the total revenue in USD from the East region in May 2026?",
    "What was the total revenue in USD from the North region in March 2026?",
    "Which product earned the most USD revenue in May 2026?",
    "Count the refunded Central orders placed in June 2026.",
    "How much was refunded in USD in the South region in April 2026?",
    "Which customer generated the highest revenue in 2026?",
]

for question in questions:
    r = requests.post(URL, json={"question": question}, timeout=60)
    print()
    print("QUESTION:", question)
    print("STATUS:", r.status_code)
    print("ANSWER:", r.text)
