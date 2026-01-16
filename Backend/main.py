from fastapi import FastAPI, Form, File, UploadFile, HTTPException
import requests
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv
import os
from typing import Optional
import json
from openai import AzureOpenAI
from pathlib import Path
from api.pre_registration import get_ai_response
from api.post_registration import post_chat
from api.post_registration import ChatRequest
from api.registration import get_bot_response
from api.registration import initialize_blob_storage
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --------------------------------------------------
# Load ENV
# --------------------------------------------------
load_dotenv()

# eligibilty_instance=EligibilityCheckRequest()
# --------------------------------------------------
# Azure OpenAI Client
# --------------------------------------------------
AZURE_CLIENT = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
)

AZURE_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")

# --------------------------------------------------
# FastAPI App
# --------------------------------------------------
app = FastAPI(title="Ladki Bahin Yojana - Smart Chat Router")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")


# Root route to serve frontend
@app.get("/")
async def root():
    """Serve the main application"""
    return FileResponse("frontend/index.html")


SESSION_MODE = {}
# --------------------------------------------------
# SMART ROUTER SYSTEM PROMPT (UPDATED)
# --------------------------------------------------
ROUTER_SYSTEM_PROMPT = """
You are a smart intent router for the Maharashtra Government scheme
"Ladki Bahin Yojana".

Your job is to classify the user’s intent into EXACTLY ONE of the
following flags:

- "eligible"
- "form_filling"
- "post_application"

You will be given:
1) The previous assistant response (prev_res) – may be empty or null
2) The current user message

You MUST consider BOTH together to determine intent.

--------------------------------------------------
CRITICAL OVERRIDE RULE – FORM FILLING (VERY IMPORTANT)
--------------------------------------------------

Route to "form_filling" ONLY if the user EXPLICITLY expresses intent
to START or DO a NEW APPLICATION.

Explicit intent phrases include (English / Hindi / Marathi examples):

- "I want to apply"
- "Apply for Ladki Bahin"
- "Start application"
- "New application"
- "Fill the form"
- "Submit application"
- "अर्ज करायचा आहे"
- "नवीन अर्ज"
- "लाडकी बहीण अर्ज भरायचा आहे"

❗ NEVER infer "form_filling" from:
- User providing data
- User answering questions
- User uploading documents
- Assistant requesting information

--------------------------------------------------
POST-APPLICATION CONTEXT OVERRIDE (CRITICAL)
--------------------------------------------------

If the previous assistant response is asking to:
- check / verify / validate / confirm
- link or confirm linkage
- fetch application status
- check payment, installment, or transaction
- troubleshoot issues after submission

AND the user responds by providing ANY of the following:
- mobile number
- Aadhaar number
- bank account number
- IFSC code
- yes / no / numeric confirmation

THEN you MUST route to "post_application",
EVEN IF the user never explicitly said they applied.

This rule OVERRIDES the "eligible" flag.

--------------------------------------------------
FLAG DEFINITIONS
--------------------------------------------------

flag_type = "eligible"
Use when:
- User is asking whether they qualify for the scheme
- User is checking eligibility rules or conditions
- Assistant is asking questions like:
  - age
  - income
  - marital status
  - residence
  - family details
- User provides personal info ONLY for eligibility determination
- Conversation is clearly BEFORE application

-------------------------------------

flag_type = "post_application"
Use when:
- User asks about application status
- Questions about payments or installments
- Aadhaar / mobile / bank / IFSC linkage AFTER submission
- Verification, validation, or tracking of an application
- User responds to verification-style questions
- Assistant uses words like:
  "check", "verify", "linked", "status", "payment",
  "installment", "transaction", "pending", "approved", "rejected"

-------------------------------------

flag_type = "form_filling"
Use ONLY when:
- User clearly and explicitly wants to APPLY
- User instructs to start, fill, or submit a NEW application

--------------------------------------------------
STRICT RULES (NON-NEGOTIABLE)
--------------------------------------------------

- Choose ONLY ONE flag
- NEVER guess or infer "form_filling"
- Data entry alone does NOT imply application intent
- Use prev_res to detect whether the user is responding
- Follow OVERRIDE rules before FLAG DEFINITIONS
- Return ONLY valid JSON
- No explanation, no extra text, no markdown

--------------------------------------------------
Output format:
{
  "flag_type": "eligible" | "form_filling" | "post_application"
}

"""
CALL_CENTER__CHATBOT_ROUTER_SYSTEM_PROMPT = """
You are a smart intent router for the Maharashtra Government scheme
"Ladki Bahin Yojana".

Your job is to classify the user’s intent into EXACTLY ONE of the
following flags:

- "eligible"
- "post_application"

You will be given:
1) The previous assistant response (prev_res) – may be empty or null
2) The current user message

You MUST consider BOTH together to determine intent.

--------------------------------------------------
POST-APPLICATION CONTEXT OVERRIDE (CRITICAL)
--------------------------------------------------

If the previous assistant response is asking to:
- check / verify / validate / confirm
- link or confirm linkage
- fetch application status
- check payment, installment, or transaction
- troubleshoot issues after submission

AND the user responds by providing ANY of the following:
- mobile number
- Aadhaar number
- bank account number
- IFSC code
- yes / no / numeric confirmation

THEN you MUST route to "post_application",
EVEN IF the user never explicitly said they applied.

This rule OVERRIDES all other rules.

--------------------------------------------------
FLAG DEFINITIONS
--------------------------------------------------

flag_type = "eligible"
Use when:
- User is asking whether they qualify for the scheme
- User is checking eligibility rules or conditions
- Assistant is asking questions like:
  - age
  - income
  - marital status
  - residence
  - family details
- User provides personal info ONLY for eligibility determination
- Conversation is clearly BEFORE application
- User expresses interest but does NOT talk about application status,
  payments, verification, or submission

-------------------------------------

flag_type = "post_application"
Use when:
- User asks about application status
- Questions about payments or installments
- Aadhaar / mobile / bank / IFSC linkage AFTER submission
- Verification, validation, or tracking of an application
- User responds to verification-style questions
- Assistant uses words like:
  "check", "verify", "linked", "status", "payment",
  "installment", "transaction", "pending", "approved", "rejected"

--------------------------------------------------
STRICT RULES (NON-NEGOTIABLE)
--------------------------------------------------

- Choose ONLY ONE flag
- Use prev_res to detect whether the user is responding
- Data sharing alone does NOT imply post-application
  UNLESS override conditions are met
- Follow OVERRIDE rules before FLAG DEFINITIONS
- Return ONLY valid JSON
- No explanation, no extra text, no markdown

--------------------------------------------------
Output format:
{
  "flag_type": "eligible" | "post_application"
}

"""


# --------------------------------------------------
# ROUTER FUNCTION (UPDATED)
# --------------------------------------------------
def route_message(message: str, prev_res: Optional[str]):
    user_payload = f"""
Previous assistant response:
{prev_res or "None"}

Current user message:
{message}
"""

    response = AZURE_CLIENT.chat.completions.create(
        model=AZURE_DEPLOYMENT,
        messages=[
            {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
            {"role": "user", "content": user_payload}
        ],
        temperature=0,
        max_tokens=50
    )

    return json.loads(response.choices[0].message.content)


def route_message_call_center(message: str, prev_res: Optional[str]):
    user_payload = f"""
Previous assistant response:
{prev_res or "None"}

Current user message:
{message}
"""

    response = AZURE_CLIENT.chat.completions.create(
        model=AZURE_DEPLOYMENT,
        messages=[
            {"role": "system", "content": CALL_CENTER__CHATBOT_ROUTER_SYSTEM_PROMPT},
            {"role": "user", "content": user_payload}
        ],
        temperature=0,
        max_tokens=50
    )

    return json.loads(response.choices[0].message.content)


@app.on_event("startup")
async def startup_event():
    try:
        logger.info("🚀 Starting application initialization...")

        if not initialize_blob_storage():
            logger.warning("⚠️ Blob storage initialization failed. Document uploads will not work.")

        logger.info("✅ Application startup complete!")

    except Exception as e:
        logger.error(f"❌ FATAL ERROR during startup: {e}")
        raise


# --------------------------------------------------
# ROUTER API (UPDATED INPUT)
# --------------------------------------------------
@app.post("/smart-chat-router-ladki-bahin")
def smart_chat_router(
        message: str = Form(...),
        session_id: str = Form(...),
        prev_res: Optional[str] = Form(None),
        aadhaar_last4: Optional[str] = Form(None),
        doc_type: Optional[str] = Form(None),
        file: Optional[UploadFile] = File(None),
        prev_res_mode: Optional[str] = Form(None)
):
    """
    Smart router for Ladki Bahin Yojana chatbot
    Uses previous response for better routing
    """
    print(f"Received message: {message}")

    if prev_res_mode == "form_filling":
        print("Previous mode was form filling")

        user_msg = message.strip().lower()

        file_uploaded = None
        if file and file.filename:
            file_uploaded = {
                "content": file.file.read(),  # sync read is OK here
                "name": file.filename,
                "extension": Path(file.filename).suffix,
                "doc_type": doc_type
            }

        # -----------------------------
        # 1. SUBMIT
        # -----------------------------
        if user_msg == "submit":
            print("User chose to submit form")
            bot_response = get_bot_response(
                session_id,
                message,
                file_uploaded
            )

            return {
                "response": bot_response,
                "mode": "Submit"
            }

        # -----------------------------
        # 2. EXIT
        # -----------------------------
        elif user_msg == "exit":
            print("User chose to exit form filling")
            final_msg_registration = "Thank you for interacting with registration agent"

            return {
                "response": final_msg_registration,
                "mode": "exit"
            }

        # -----------------------------
        # 3. CONTINUE FORM FILLING
        # -----------------------------
        else:
            print("Else - continue form filling")
            bot_response = get_bot_response(
                session_id,
                message,
                file_uploaded
            )

            return {
                "response": bot_response,
                "mode": "form_filling"
            }

    routing_result = route_message(message, prev_res)
    print(f"Routing result: {routing_result}")

    route = routing_result["flag_type"]

    if route == 'eligible':
        print("Routed to Eligibility Agent")

        ai_response = get_ai_response(
            session_id=session_id,
            user_message=message
        )

        structured_response = {
            "response": {
                "response": ai_response
            },
            "mode": "eligible"
        }

        return structured_response





    elif route == 'form_filling':
        print("Routed to Form Filling Agent")
        SESSION_MODE[session_id] = "form_filling"

        # first_response_form_filling = (
        #     "We welcome you to Agripilot for filling chatbot. "
        #     "Kindly give your full name."
        # )

        first_response_form_filling = (
            "Kindly select your preferred language / कृपया आपली प्राधान्य भाषा निवडा / कृपया अपनी पसंदीदा भाषा चुनें:\n"

        )

        # first_response_form_filling=(
        #     "🙏 नमस्कार! लाडकी बहीण योजनेत आपले स्वागत आहे!\n🙏 नमस्कार! लाडकी बहन योजना में आपका स्वागत है!\n"
        #     "🙏 Welcome to Ladki Bahin Yojana!\n\n✅ आपण या योजनेसाठी पात्र आहात!\n✅ आप इस योजना के लिए पात्र हैं!"
        #     "\n✅ You are eligible for this scheme!"
        # )

        return {
            "response": first_response_form_filling,
            "mode": "form_filling"
        }



    elif route == 'post_application':
        print("Routed to Post Application Agent")
        res_post_application = post_chat(ChatRequest(
            session_id=session_id,
            message=message,
            aadhaar_last4=aadhaar_last4,

        ))
        print(f"Post Application Agent Response: {res_post_application}")

        return {
            "response": res_post_application,
            "mode": "post_application"
        }

    return {
        "session_id": session_id,
        "flag_type": routing_result["flag_type"]
    }


@app.post("/call-center-smart-chat-router-ladki-bahin")
def call_center_smart_chat_router(
        message: str = Form(...),
        session_id: str = Form(...),
        prev_res: Optional[str] = Form(None),
        aadhaar_last4: Optional[str] = Form(None),
        prev_res_mode: Optional[str] = Form(None)
):
    """
    Smart router for Ladki Bahin Yojana chatbot
    Uses previous response for better routing
    """
    print(f"Received message: {message}")

    routing_result = route_message_call_center(message, prev_res)
    print(f"Routing result: {routing_result}")

    route = routing_result["flag_type"]

    if route == 'eligible':
        print("Routed to Eligibility Agent")

        ai_response = get_ai_response(
            session_id=session_id,
            user_message=message
        )

        structured_response = {
            "response": {
                "response": ai_response
            },
            "mode": "eligible"
        }

        return structured_response



    elif route == 'post_application':
        print("Routed to Post Application Agent")
        res_post_application = post_chat(ChatRequest(
            session_id=session_id,
            message=message,
            aadhaar_last4=aadhaar_last4,

        ))
        print(f"Post Application Agent Response: {res_post_application}")

        return {
            "response": res_post_application,
            "mode": "post_application"
        }

    return {
        "session_id": session_id,
        "flag_type": routing_result["flag_type"]
    }


# --------------------------------------------------
# RUN
# --------------------------------------------------
# --------------------------------------------------
# SPEECH TOKEN API
# --------------------------------------------------
@app.get("/api/speech-token")
async def get_speech_token():
    """Get Azure Speech token with enhanced error handling"""
    speech_key = os.getenv("AZURE_SPEECH_KEY")
    service_region = os.getenv("AZURE_SPEECH_REGION", "centralindia")

    if not speech_key:
        raise HTTPException(status_code=500, detail="Azure Speech API Key not configured")

    if not service_region:
        raise HTTPException(status_code=500, detail="Azure Speech Region not configured")

    fetch_token_url = f"https://{service_region}.api.cognitive.microsoft.com/sts/v1.0/issueToken"
    headers = {
        'Ocp-Apim-Subscription-Key': speech_key
    }

    try:
        response = requests.post(fetch_token_url, headers=headers, timeout=10)

        if response.status_code == 200:
            return {
                "token": response.text,
                "region": service_region,
                "success": True
            }
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to retrieve token: {response.text}"
            )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error connecting to speech service: {str(e)}"
        )


from api.text_to_speech import text_to_speech
from fastapi.responses import Response
from api.text_to_speech import text_to_speech_gemini
# ... existing code ...

@app.post("/api/tts")
async def generate_tts(request: dict):
    """
    Generate speech from text using Gemini 2.5 TTS
    """
    try:
        text = request.get("text")
        api_key = os.getenv("GOOGLE_API_KEY")
        if not text:
            raise HTTPException(status_code=400, detail="Text is required")
            
        # Detect language logic can be enhanced, defaulting to 'en-IN' or 'hi-IN' based on text if needed
        # For now, let's pass a default or let the function handle it. 
        # The existing function signature is text_to_speech(text, language_code="en-IN", ...)
        
        audio_content = text_to_speech_gemini(filename="output.wav", api_key=api_key, text=text)
        
        if not audio_content:
             raise HTTPException(status_code=500, detail="Failed to generate audio")

        return Response(content=audio_content, media_type="audio/mp3")

    except Exception as e:
        logger.error(f"TTS Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=9015, reload=True)