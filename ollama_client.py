import requests
from config import OLLAMA_URL, MODEL, TEMPERATURE

def ask_ollama(prompt, model=MODEL, temperature=TEMPERATURE):
    payload = {"model": model, "prompt": prompt, "stream": False}
    if temperature is not None:
        payload["options"] = {"temperature": temperature}
    response = requests.post(OLLAMA_URL, json=payload)
    response.raise_for_status()
    return response.json()["response"]

if __name__ == "__main__":
    answer = ask_ollama("Say hello in five words.")
    print(answer)
