import os
import sys
import requests
import json
from pathlib import Path
from deep_translator import GoogleTranslator
import argostranslate.translate
import argostranslate.package

def load_app_environment():
    if getattr(sys, "frozen", False):
        env_path = Path(sys.executable).resolve().parent / ".env"
    else:
        env_path = Path(__file__).resolve().with_name(".env")
    if not env_path.exists():
        return

    with env_path.open(encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            name = name.strip()
            if not name or any(char.isspace() for char in name):
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            os.environ.setdefault(name, value)


load_app_environment()

def log_translation_message(message):
    try:
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "translation.log")
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except Exception as log_ex:
        print(f"Failed to write to log: {log_ex}")

def get_settings():
    # Print this just once to verify it sees the key
    api_key = os.environ.get("GEMINI_API_KEY")
    
    return {
        "gemini_api_key": api_key,
        "cloudflare_account_id": os.environ.get("CLOUDFLARE_ACCOUNTID", ""),
        "cloudflare_api_key": os.environ.get("CF_WORKERSAI_REST_API") or os.environ.get("CF_ACCOUNT_API_Token", "")
    }

def translate_gemini(text, source_lang, target_lang):
    settings = get_settings()
    if not settings["gemini_api_key"]:
        raise Exception("Gemini API key missing in .env")
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={settings['gemini_api_key']}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{
            "parts": [{
                "text": f"Translate this text to {target_lang} (respond only with the translation, no extra text): {text}"
            }]
        }]
    }
    response = requests.post(url, json=payload, headers=headers, timeout=10)
    log_translation_message(f"Gemini Response Code: {response.status_code}")
    if response.status_code == 200:
        res_json = response.json()
        try:
            return res_json['candidates'][0]['content']['parts'][0]['text'].strip()
        except KeyError:
            raise Exception(f"Unexpected Gemini response structure: {json.dumps(res_json)}")
    raise Exception(f"Gemini API failed with status {response.status_code}: {response.text}")

def translate_cloudflare(text, source_lang, target_lang):
    settings = get_settings()
    url = f"https://api.cloudflare.com/client/v4/accounts/{settings['cloudflare_account_id']}/ai/run/@cf/meta/llama-3.1-8b-fast-v2"
    headers = {"Authorization": f"Bearer {settings['cloudflare_api_key']}", "Content-Type": "application/json"}
    payload = {"messages": [{"role": "user", "content": f"Translate to {target_lang}: {text}"}]}
    
    response = requests.post(url, json=payload, headers=headers, timeout=10)
    log_translation_message(f"Cloudflare Response Code: {response.status_code}")
    if response.status_code == 200:
        return response.json()['result']['response']
    raise Exception(f"Cloudflare failed: {response.status_code}")

def translate_perchance(text_ignored, source_lang, target_lang, image_path):
    # Note: Added image_path since this is a vision-capable model
    settings = get_settings()
    api_url = settings.get("perchance_endpoint", "https://api.perchance.org/ai/chat")
    api_key = settings.get("perchance_api_key", "")
    
    # Use your existing encode_image helper
    base64_image = encode_image(image_path)
    
    payload = {
        "model": "gpt-4o", # Check the generator's specific model requirement
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": "Read the Japanese text and provide a natural English translation."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ]
        }],
        "max_tokens": 500
    }
    
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    response = requests.post(api_url, headers=headers, json=payload, timeout=20)
    
    if response.status_code == 200:
        return response.json()['choices'][0]['message']['content']
    raise Exception(f"Perchance AI failed: {response.status_code}")

def translate_google(text, source_lang, target_lang):
    return GoogleTranslator(source='auto', target='en').translate(text)

def translate_offline(text, source_lang, target_lang):
    # Mapping to argos codes if necessary
    return argostranslate.translate.translate(text, source_lang, target_lang)

# Main Entry Point
def get_best_translation(text, source_lang, target_lang, priority_list):
    log_translation_message(f"Starting translation. Text: {repr(text)}, Src: {source_lang}, Target: {target_lang}, Priority: {priority_list}")
    for provider in priority_list:
        try:
            log_translation_message(f"Trying provider: {provider}")
            if provider == "cloudflare": 
                res = translate_cloudflare(text, source_lang, target_lang)
            elif provider == "gemini": 
                res = translate_gemini(text, source_lang, target_lang)
            elif provider == "google": 
                res = translate_google(text, source_lang, target_lang)
            elif provider == "offline": 
                res = translate_offline(text, source_lang, target_lang)
            else:
                raise Exception(f"Unknown provider: {provider}")
            log_translation_message(f"Provider {provider} succeeded: {repr(res)}")
            return res
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            log_translation_message(f"Provider {provider} failed: {e}\nTraceback:\n{tb}")
            print(f"Provider {provider} failed: {e}")
            continue
    log_translation_message("All providers failed.")
    return f"Translation failed: {text}"