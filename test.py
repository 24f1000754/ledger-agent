import requests

questions = [
    "What was the total revenue from the North region in March 2026?",
    "How much revenue did the South region generate in April 2026?",
    "What were the refunds in the East region in May 2026?",
    "How many orders were there in the West region in June 2026?"
]

for question in questions:

    response = requests.post(
        "http://127.0.0.1:5000/answer",
        json={
            "question": question
        }
    )

    print()
    print("QUESTION:", question)
    print("ANSWER:", response.json())