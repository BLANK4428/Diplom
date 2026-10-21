import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "gemma3:12b"

def ask_llm(prompt):
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": 350,   # limit output tokens — JSON is short
                "temperature": 0.1,   # near-deterministic = faster
                "top_k": 20,
            }
        },
        timeout=120
    )
    return response.json()["response"]