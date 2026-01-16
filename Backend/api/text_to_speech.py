import requests
import base64
import wave
import json

def text_to_speech_gemini(text, filename="output.wav", api_key="YOUR_API_KEY"):
    model_name = "gemini-2.5-flash-preview-tts"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"

    # The prompt can include "Director's Notes" for better expression
    prompt_text = f"Say cheerfully: {text}"

    payload = {
        "contents": [{
            "parts": [{"text": prompt_text}]
        }],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": "Aoede" # Options: 'Puck', 'Charon', 'Kore', 'Fenrir', 'Aoede', etc.
                    }
                }
            }
        }
    }

    response = requests.post(url, json=payload)
    
    if response.status_code == 200:
        data = response.json()
        try:
            # Extract base64 audio data
            audio_b64 = data['candidates'][0]['content']['parts'][0]['inlineData']['data']
            audio_bytes = base64.b64decode(audio_b64)

            # Gemini TTS returns raw PCM (16-bit LE, 24kHz, Mono). 
            # We must wrap it in a WAV container to make it playable.
            with wave.open(filename, "wb") as wf:
                wf.setnchannels(1)          # Mono
                wf.setsampwidth(2)          # 16-bit (2 bytes)
                wf.setframerate(24000)      # 24kHz
                wf.writeframes(audio_bytes)
            
            print(f"Success! Saved to {filename}")
            return True
        except (KeyError, IndexError) as e:
            print(f"Error parsing response: {e}")
            print(json.dumps(data, indent=2))
    else:
        print(f"API Error {response.status_code}: {response.text}")
    return False

# Usage
# text_to_speech_gemini("Hello! I am speaking using the Gemini native TTS model.", api_key="AIzaSy...")