# config.py - Azure Speech Services Configuration
import os
import audioop
import azure.cognitiveservices.speech as speechsdk
import base64
from dotenv import load_dotenv
from pydub.playback import play
import io
from pydub import AudioSegment

load_dotenv()

# Initialize Azure Speech Config
speech_config = speechsdk.SpeechConfig(
    subscription=os.getenv("AZURE_SPEECH_KEY"),
    region=os.getenv("AZURE_SPEECH_REGION")
)

# speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config)
speech_config.speech_synthesis_voice_name = "en-US-JennyNeural"


def azure_text_to_speech(text, lang_code='en-US'):
    """
    Convert text to speech using Azure Speech Services

    Args:
        text (str): Text to convert to speech
        lang_code (str): Language code (default: 'en-US')

    Returns:
        bytes: Raw PCM16 audio bytes in mu-law format (8kHz)
    """
    # Select voice based on language
    if lang_code == 'hi-IN':
        speech_config.speech_synthesis_voice_name = "hi-IN-SwaraNeural"
    else:
        speech_config.speech_synthesis_voice_name = "en-US-EmmaMultilingualNeural"

    # Create synthesizer with no audio output (we'll handle it ourselves)
    synthesizer = speechsdk.SpeechSynthesizer(
        speech_config=speech_config,
        audio_config=None
    )

    # Synthesize speech
    result = synthesizer.speak_text_async(text).get()

    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        # Convert PCM16 16kHz to mu-law 8kHz for Plivo
        pcm16_bytes = result.audio_data
        ulaw_bytes = audioop.lin2ulaw(
            audioop.ratecv(pcm16_bytes, 2, 1, 16000, 8000, None)[0], 2
        )
        return ulaw_bytes
    else:
        raise Exception(f"Speech synthesis failed: {result.reason}")


def play_audio_from_base64(audio_base64):
    """
    Decode base64 audio and play it (for testing)

    Args:
        audio_base64 (str): Base64-encoded audio data
    """
    if audio_base64 is None:
        return

    audio_bytes = base64.b64decode(audio_base64)
    audio = AudioSegment.from_wav(io.BytesIO(audio_bytes))
    play(audio)

#
# def create_azure_speech_recognizer():
#     """
#     Create Azure Speech Recognizer for speech-to-text
#
#     Returns:
#         tuple: (recognizer, stream) - Speech recognizer and audio stream
#     """
#     # Configure audio format (16kHz, 16-bit PCM)
#     audio_format = speechsdk.audio.AudioStreamFormat(
#         samples_per_second=16000,
#         bits_per_sample=16,
#         wave_stream_format=speechsdk.audio.AudioStreamWaveFormat.PCM
#     )
#
#     # Create push audio input stream
#     stream = speechsdk.audio.PushAudioInputStream(stream_format=audio_format)
#
#     # Create audio config from stream
#     audio_config = speechsdk.audio.AudioConfig(stream=stream)
#
#     # Create speech recognizer
#     recognizer = speechsdk.SpeechRecognizer(
#         speech_config=speech_config,
#         audio_config=audio_config
#     )
#
#     return recognizer, stream
def create_azure_speech_recognizer():
    """
    Create Azure Speech Recognizer with auto language detection
    Supports: English, Hindi, Marathi
    """

    audio_format = speechsdk.audio.AudioStreamFormat(
        samples_per_second=16000,
        bits_per_sample=16,
        wave_stream_format=speechsdk.audio.AudioStreamWaveFormat.PCM
    )

    stream = speechsdk.audio.PushAudioInputStream(stream_format=audio_format)
    audio_config = speechsdk.audio.AudioConfig(stream=stream)

    # 🔥 Auto-detect languages
    auto_detect_config = speechsdk.languageconfig.AutoDetectSourceLanguageConfig(
        languages=[
            "en-IN",   # English (India)
            "hi-IN",   # Hindi
            "mr-IN"    # Marathi
        ]
    )

    recognizer = speechsdk.SpeechRecognizer(
        speech_config=speech_config,
        audio_config=audio_config,
        auto_detect_source_language_config=auto_detect_config
    )

    return recognizer, stream
