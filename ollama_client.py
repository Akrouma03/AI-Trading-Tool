import requests
from config import OLLAMA_URL, MODEL, TEMPERATURE, OLLAMA_TIMEOUT, THINKING


def generate(prompt, model=MODEL, temperature=TEMPERATURE, thinking=THINKING):
    """Run one completion. Returns {"response", "thinking", "model"}.

    Ollama keeps a thinking model's reasoning in a separate "thinking" field,
    so it never shows up in the answer -- and was being discarded, even though
    that reasoning is what this project set out to study. "model" is echoed
    back by Ollama so a decision is logged against the model that actually
    produced it rather than whatever config.MODEL happens to say.
    """
    payload = {"model": model, "prompt": prompt, "stream": False, "keep_alive": "2h"}
    if temperature is not None:
        payload["options"] = {"temperature": temperature}
    if thinking is not None:
        payload["think"] = thinking
    response = requests.post(OLLAMA_URL, json=payload, timeout=OLLAMA_TIMEOUT)
    response.raise_for_status()
    body = response.json()
    return {
        "response": body["response"],
        "thinking": body.get("thinking") or "",
        "model": body.get("model") or model,
    }


def ask_ollama(prompt, **kwargs):
    """Just the answer text."""
    return generate(prompt, **kwargs)["response"]


if __name__ == "__main__":
    result = generate("Say hello in five words.")
    print("model:   ", result["model"])
    print("answer:  ", result["response"])
    print("thinking:", len(result["thinking"]), "chars")
