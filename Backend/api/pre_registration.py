"""
Ladki Bahin Yojana - Eligibility Agent FastAPI Backend
POC Demo for Maharashtra Government Scheme
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import Optional, Dict, Any, List, Set
from openai import AzureOpenAI
import requests
from dotenv import load_dotenv
from eligibility_rules import ELIGIBILITY_RULES, ELIGIBILITY_QUESTIONS
import asyncio
import audioop
import base64
from datetime import datetime, date
import json
import os
import traceback
from typing import Optional
from urllib.parse import parse_qs
from starlette.websockets import WebSocketState, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi import FastAPI, WebSocket, Request, HTTPException
from starlette.responses import HTMLResponse
from plivo import plivoxml
from config import create_azure_speech_recognizer, azure_text_to_speech
from database import get_user_by_phone
from models import (
    ChatRequest,
    ChatResponse,
)
import azure.cognitiveservices.speech as speechsdk

load_dotenv()

app = FastAPI(
    title="Ladki Bahin Yojana - Eligibility Agent API",
    description="AI-powered eligibility checker for Maharashtra's Mukhyamantri Majhi Ladki Bahin Yojana",
    version="1.0.0"
)

# CORS - Allow all origins for development (restrict in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
# app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

# Initialize Azure OpenAI client
client = AzureOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version="2024-12-01-preview"
)

# Store conversation sessions (in-memory for POC)
sessions: Dict[str, Dict] = {}
HOST_URL = os.getenv('HOST_URL', 'wss://your-domain.com')

voice_sessions = {}

call_center_clients: Set[WebSocket] = set()

class ConnectCallModel(BaseModel):
    ActionMode: int
    UserID: int
    TokenID: Optional[int] = None
# System prompt for the Eligibility Agent
SYSTEM_PROMPT = """You are the "Ladki Bahin Eligibility Agent" (लाडकी बहीण पात्रता सहाय्यक) - an AI assistant for Maharashtra's Mukhyamantri Majhi Ladki Bahin Yojana scheme.

Your capabilities:
1. Check eligibility for the scheme based on user's information
2. Provide step-by-step guidance for application
3. Answer questions about the scheme in English, Hindi, or Marathi
4. Explain eligibility and ineligibility criteria clearly

SCHEME RULES:
- Monthly Benefit: ₹1,500 (proposed increase to ₹2,100)
- Age: 21-65 years
- Gender: Female only
- Residency: Maharashtra permanent resident
- Income: Annual family income ≤ ₹2.5 lakh
- Marital Status: Married, Widowed, Divorced, Abandoned, or Unmarried (1 per family)
- Max 2 women per household can receive benefits

INELIGIBILITY (if ANY apply, person is NOT eligible):
- Any family member pays income tax
- Any family member is permanent government employee
- Any family member receives government pension
- Any family member is MP/MLA/Board Chairman/Director
- Family owns four-wheeler (tractor exempted)
- Already receiving ₹1,500+ from another government scheme

REQUIRED DOCUMENTS:
- Aadhaar Card (linked to bank & mobile)
- Bank Passbook (own account, not joint, DBT enabled)
- Passport Photo
- Residency Proof (Domicile/15-yr old Ration Card/Voter ID)
- Income Certificate (only for white ration card holders)

OFFICIAL PORTALS:
- Main: ladakibahin.maharashtra.gov.in
- e-KYC: ladakibahin.maharashtra.gov.in/ekyc/
- Helpline: 181, 1800-120-8040

BEHAVIOR:
1. ENTIRE response must be in user's language (English/Hindi/Marathi) - including verdict
2. Be EXTREMELY concise - max 2-3 short sentences or bullet points
3. NO greetings, pleasantries, or filler words
4. NO explanations unless user explicitly asks "why" or "explain"
5. Use bullet points for lists
6. Ask ONE eligibility question at a time

ELIGIBILITY CHECK SEQUENCE (MANDATORY - must verify ALL before verdict):
1. Gender (female only)
2. Age (21-65 years)
3. Maharashtra permanent resident
4. Annual family income (≤₹2.5 lakh)
5. Any family member pays income tax? (must be NO)
6. Any family member is govt employee? (must be NO)
7. Any family member receives pension? (must be NO)
8. Any family member is MP/MLA/Board member? (must be NO)
9. Family owns four-wheeler? (must be NO, tractor exempt)
10. Already receiving ₹1,500+/month from other scheme? (must be NO)

CRITICAL RULE: NEVER declare "ELIGIBLE/पात्र" until ALL 10 criteria above are verified. If user skips questions, ask the pending ones.

STATUS VERDICT (only after ALL checks complete):
- English: "✅ ELIGIBLE" / "❌ NOT ELIGIBLE: [reason]"
- Marathi: "✅ पात्र" / "❌ अपात्र: [कारण]"
- Hindi: "✅ पात्र" / "❌ अपात्र: [कारण]"

If any single criterion fails, immediately declare NOT ELIGIBLE with reason.
For complex cases: contact helpline 181
"""



class EligibilityCheckRequest(BaseModel):
    age: Optional[int] = None
    gender: Optional[str] = None
    income: Optional[float] = None
    maharashtra_resident: Optional[bool] = None
    income_tax_payer: Optional[bool] = False
    govt_employee: Optional[bool] = False
    govt_pension: Optional[bool] = False
    political_position: Optional[bool] = False
    four_wheeler: Optional[bool] = False
    existing_benefit: Optional[bool] = False


class ResetRequest(BaseModel):
    session_id: str = "default"


def get_ai_response(session_id: str, user_message: str) -> str:
    """Get response from Azure OpenAI for the eligibility agent"""
    
    # Initialize session if new
    if session_id not in sessions:
        sessions[session_id] = {
            "messages": [],
            "eligibility_status": None,
            "checked_criteria": {}
        }
    
    # Add user message to history
    sessions[session_id]["messages"].append({
        "role": "user",
        "content": user_message
    })
    
    try:
        # Build messages with system prompt
        messages_with_system = [{"role": "system", "content": SYSTEM_PROMPT}] + sessions[session_id]["messages"]
        
        # Call Azure OpenAI API
        response = client.chat.completions.create(
            model=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
            max_tokens=1024,
            messages=messages_with_system
        )
        
        assistant_message = response.choices[0].message.content
        
        # Add assistant response to history
        sessions[session_id]["messages"].append({
            "role": "assistant",
            "content": assistant_message
        })
        
        return assistant_message
        
    except Exception as e:
        return f"Error: {str(e)}. Please check your API key."


def check_eligibility_rule(criteria: str, value: Any) -> tuple:
    """Check a specific eligibility rule"""
    rules = ELIGIBILITY_RULES
    
    if criteria == "age":
        age = int(value)
        if rules["age"]["min"] <= age <= rules["age"]["max"]:
            return True, "Age criteria met ✅"
        return False, f"Age must be between {rules['age']['min']} and {rules['age']['max']} years ❌"
    
    elif criteria == "income":
        income = float(value)
        if income <= rules["income"]["max_annual"]:
            return True, "Income criteria met ✅"
        return False, f"Annual family income exceeds ₹{rules['income']['max_annual']:,} ❌"
    
    elif criteria == "gender":
        if value.lower() in ["female", "f", "महिला", "स्त्री"]:
            return True, "Gender criteria met ✅"
        return False, "Only female applicants are eligible ❌"
    
    elif criteria == "residency":
        if value.lower() in ["yes", "हो", "हां", "maharashtra"]:
            return True, "Residency criteria met ✅"
        return False, "Must be Maharashtra permanent resident ❌"
    
    return None, "Unknown criteria"


@app.get("/")
async def root():
    """Serve the main application"""
    return FileResponse("frontend/index.html")


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Handle chat messages"""
    if not request.message:
        raise HTTPException(status_code=400, detail="Message is required")
    
    response = get_ai_response(request.session_id, request.message)
    
    return ChatResponse(
        response=response,
        session_id=request.session_id
    )


@app.post("/api/check-eligibility")
async def check_eligibility(request: EligibilityCheckRequest):
    """Direct eligibility check API"""
    results = {
        "eligible": True,
        "checks": [],
        "failed_criteria": []
    }
    
    # Check each provided criterion
    if request.age is not None:
        passed, msg = check_eligibility_rule("age", request.age)
        results["checks"].append({"criterion": "age", "passed": passed, "message": msg})
        if not passed:
            results["eligible"] = False
            results["failed_criteria"].append("age")
    
    if request.gender is not None:
        passed, msg = check_eligibility_rule("gender", request.gender)
        results["checks"].append({"criterion": "gender", "passed": passed, "message": msg})
        if not passed:
            results["eligible"] = False
            results["failed_criteria"].append("gender")
    
    if request.income is not None:
        passed, msg = check_eligibility_rule("income", request.income)
        results["checks"].append({"criterion": "income", "passed": passed, "message": msg})
        if not passed:
            results["eligible"] = False
            results["failed_criteria"].append("income")
    
    if request.maharashtra_resident is not None:
        passed, msg = check_eligibility_rule("residency", "yes" if request.maharashtra_resident else "no")
        results["checks"].append({"criterion": "residency", "passed": passed, "message": msg})
        if not passed:
            results["eligible"] = False
            results["failed_criteria"].append("residency")
    
    # Check ineligibility criteria
    ineligibility_checks = [
        ("income_tax_payer", request.income_tax_payer, "Family member pays income tax"),
        ("govt_employee", request.govt_employee, "Family member is government employee"),
        ("govt_pension", request.govt_pension, "Family member receives government pension"),
        ("political_position", request.political_position, "Family member holds political position"),
        ("four_wheeler", request.four_wheeler, "Family owns four-wheeler vehicle"),
        ("existing_benefit", request.existing_benefit, "Already receiving ₹1500+ from another scheme")
    ]
    
    for key, value, description in ineligibility_checks:
        if value:
            results["eligible"] = False
            results["failed_criteria"].append(key)
            results["checks"].append({
                "criterion": key,
                "passed": False,
                "message": f"{description} - NOT ELIGIBLE ❌"
            })
    
    # Final verdict
    if results["eligible"]:
        results["verdict"] = "🎉 Congratulations! You appear to be ELIGIBLE for Ladki Bahin Yojana!"
        results["next_steps"] = [
            "Visit ladakibahin.maharashtra.gov.in to apply",
            "Keep your Aadhaar card, bank passbook, and residency proof ready",
            "Complete e-KYC verification",
            "For help, call 181 or 1800-120-8040"
        ]
    else:
        results["verdict"] = "❌ Sorry, based on the information provided, you are NOT ELIGIBLE for Ladki Bahin Yojana."
        results["reason"] = f"Failed criteria: {', '.join(results['failed_criteria'])}"
    
    return results


@app.get("/api/questions")
async def get_questions():
    """Get eligibility check questions"""
    return ELIGIBILITY_QUESTIONS


@app.get("/api/rules")
async def get_rules():
    """Get eligibility rules"""
    return ELIGIBILITY_RULES


@app.post("/api/reset")
async def reset_session(request: ResetRequest):
    """Reset a chat session"""
    if request.session_id in sessions:
        del sessions[request.session_id]
    
    return {"status": "Session reset successfully"}


@app.get("/api/speech-token")
async def get_speech_token():
    """Get Azure Speech token with enhanced error handling and multi-language support"""
    speech_key = os.getenv("AZURE_SPEECH_KEY")
    service_region = os.getenv("AZURE_SPEECH_REGION", "centralindia")
    
    # Detailed error messages for missing credentials
    if not speech_key:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Azure Speech API Key not configured",
                "details": "Please set AZURE_SPEECH_KEY in your .env file",
                "success": False
            }
        )
    
    if not service_region:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Azure Speech Region not configured",
                "details": "Please set AZURE_SPEECH_REGION in your .env file (e.g., centralindia)",
                "success": False
            }
        )

    fetch_token_url = f"https://{service_region}.api.cognitive.microsoft.com/sts/v1.0/issueToken"
    headers = {
        'Ocp-Apim-Subscription-Key': speech_key
    }
    
    try:
        # Add timeout to prevent hanging
        response = requests.post(fetch_token_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            return {
                "token": response.text,
                "region": service_region,
                "success": True
            }
        elif response.status_code == 401:
            raise HTTPException(
                status_code=401,
                detail={
                    "error": "Invalid Azure Speech API Key",
                    "details": "The API key is incorrect. Please verify AZURE_SPEECH_KEY",
                    "success": False
                }
            )
        elif response.status_code == 403:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Access Forbidden",
                    "details": "Check your Azure Speech Service permissions and subscription",
                    "success": False
                }
            )
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail={
                    "error": "Failed to retrieve token",
                    "status_code": response.status_code,
                    "details": response.text,
                    "success": False
                }
            )
            
    except requests.exceptions.Timeout:
        raise HTTPException(
            status_code=504,
            detail={
                "error": "Request timeout",
                "details": "Azure Speech Service took too long to respond. Please try again",
                "success": False
            }
        )
    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Connection error",
                "details": "Unable to connect to Azure Speech Service. Check your internet connection",
                "success": False
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Unexpected error",
                "details": str(e),
                "success": False
            }
        )

@app.api_route("/incoming-call", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    """Handle incoming Plivo call and setup voice interface"""
    try:
        form_data = await request.form()
        caller_phone = form_data.get("From", "unknown")
        call_uuid = form_data.get("CallUUID", f"call_{datetime.now().timestamp()}")

        # Validate beneficiary by mobile number
        user_details = get_user_by_phone(caller_phone)

        # Use BeneficiaryId
        beneficiary_id = user_details.get("BeneficiaryId", f"unknown_{datetime.now().timestamp()}")

        # Create session
        session_data = {
            "beneficiary_id": beneficiary_id,
            "caller_phone": caller_phone,
            "call_uuid": call_uuid,
            "session_id": f"{beneficiary_id}_{call_uuid}",
            "call_start": datetime.now(),
            "conversation_history": []
        }

        voice_sessions[str(beneficiary_id)] = session_data

        print(f"✅ Session created for beneficiary_id: {beneficiary_id}")

        # Serialize user_details for JSON (convert dates to strings)
        safe_user_info = {}
        if user_details:
            for key, value in user_details.items():
                if isinstance(value, (datetime, date)):
                    safe_user_info[key] = value.isoformat()
                else:
                    safe_user_info[key] = value

        # ⭐ IMPORTANT: Broadcast call_started event
        await broadcast_to_call_center({
            "type": "call_started",
            "call": {
                "beneficiary_id": beneficiary_id,
                "caller_phone": caller_phone,
                "call_uuid": call_uuid,
                "session_id": f"{beneficiary_id}_{call_uuid}",
                "call_start": session_data["call_start"].isoformat(),
                "conversation_history": [],
                "user_info": safe_user_info.get("FullName", "Unknown User")  # Send just the name
            }
        })

        print(f"📢 Broadcasted call_started for {beneficiary_id}")

        await asyncio.sleep(0.1)

        # Greeting
        user_name = ""
        if user_details and user_details.get("FullName"):
            user_name = user_details["FullName"].split()[0]

        greeting = "नमस्कार"
        if user_name:
            greeting += f" {user_name}"
        greeting += (
            "! लाडकी बहिणी योजनेच्या व्हॉईस सहाय्यकात आपले स्वागत आहे. "
            "मी आज आपली कशी मदत करू?"
        )

        response = plivoxml.ResponseElement()
        response.add(plivoxml.SpeakElement(
            greeting,
            voice="Polly.Aditi",
            language="mr-IN"
        ))

        # WebSocket stream
        ws_url = f"{HOST_URL}/media-stream?beneficiary_id={beneficiary_id}"
        print(f"🔗 WebSocket URL: {ws_url}")

        response.add(plivoxml.StreamElement(
            ws_url,
            bidirectional=True,
            streamTimeout=86400,
            keepCallAlive=True,
            contentType="audio/x-mulaw;rate=8000",
            audioTrack="inbound"
        ))

        xml_response = '<?xml version="1.0" encoding="UTF-8"?>\n' + response.to_string()
        return HTMLResponse(xml_response, media_type="application/xml")

    except Exception as e:
        print(f"❌ Error in incoming call: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")
@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    """Handle Plivo media stream for voice interaction"""

    await websocket.accept()
    print("✅ WebSocket accepted")

    # Read beneficiary_id
    query_params = parse_qs(websocket.url.query)
    beneficiary_id_param = query_params.get("beneficiary_id", [None])[0]

    if not beneficiary_id_param:
        await websocket.close(code=1008, reason="Missing beneficiary_id")
        return

    beneficiary_id_str = str(beneficiary_id_param)
    print(f"🔍 Looking for session: {beneficiary_id_str}")

    # Wait for session
    session = None
    for _ in range(20):
        if beneficiary_id_str in voice_sessions:
            session = voice_sessions[beneficiary_id_str]
            break
        await asyncio.sleep(0.5)

    if not session:
        await websocket.close(code=1008, reason="Session not found")
        return

    print(f"🎙️ Voice session started for beneficiary_id {beneficiary_id_str}")

    # Create Azure recognizer
    recognizer, stream = create_azure_speech_recognizer()

    processing_response = False
    loop = asyncio.get_running_loop()
    def recognizing_handler(evt):
        partial = evt.result.text.strip()
        if partial:
            print(f"[Partial] {partial}")

    def recognized_handler(evt):
        nonlocal processing_response

        if evt.result.reason != speechsdk.ResultReason.RecognizedSpeech:
            return

        final_text = evt.result.text.strip()

        # Ignore empty / silence
        if not final_text:
            print("🔇 Empty speech detected, skipping AI call")
            return

        if processing_response:
            print("⚠️ Already processing, skipping...")
            return

        processing_response = True

        detected_lang = evt.result.properties.get(
            speechsdk.PropertyId.SpeechServiceConnection_AutoDetectSourceLanguageResult
        )

        print(f"🗣️ [{detected_lang}] User said: {final_text}")

        # Save user message
        user_message = {
            "role": "user",
            "message": final_text,
            "timestamp": datetime.now().isoformat()
        }
        session["conversation_history"].append(user_message)

        # ⭐ IMPORTANT: Broadcast transcript update immediately after user message
        asyncio.run_coroutine_threadsafe(
            broadcast_to_call_center({
                "type": "transcript_update",
                "beneficiary_id": beneficiary_id_str,
                "conversation_history": session["conversation_history"]
            }),
            loop
        )

        async def process_chat():
            nonlocal processing_response
            try:
                reply = get_ai_response(
                    session_id=session["session_id"],
                    user_message=final_text,
                )

                print("Assistant:", reply)

                # Save assistant message
                assistant_message = {
                    "role": "bot",  # Changed from "bot" to "assistant" for consistency
                    "message": reply,
                    "timestamp": datetime.now().isoformat()
                }
                session["conversation_history"].append(assistant_message)

                # ⭐ IMPORTANT: Broadcast transcript update after assistant response
                await broadcast_to_call_center({
                    "type": "transcript_update",
                    "beneficiary_id": beneficiary_id_str,
                    "conversation_history": session["conversation_history"]
                })

                # Convert text to speech and send to caller
                audio = azure_text_to_speech(reply)
                audio_b64 = base64.b64encode(audio).decode("utf-8")

                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json({
                        "event": "playAudio",
                        "media": {
                            "contentType": "audio/x-mulaw",
                            "sampleRate": 8000,
                            "payload": audio_b64
                        }
                    })

            except Exception as e:
                print(f"❌ Chat error: {e}")
                traceback.print_exc()
            finally:
                processing_response = False

        asyncio.run_coroutine_threadsafe(process_chat(), loop)

    recognizer.recognizing.connect(recognizing_handler)
    recognizer.recognized.connect(recognized_handler)
    recognizer.start_continuous_recognition()

    try:
        async for message in websocket.iter_text():
            data = json.loads(message)

            if data.get("event") == "media":
                audio = base64.b64decode(data["media"]["payload"])
                audio = audioop.ulaw2lin(audio, 2)
                audio = audioop.ratecv(audio, 2, 1, 8000, 16000, None)[0]
                stream.write(audio)

            elif data.get("event") == "stop":
                break

    finally:
        recognizer.stop_continuous_recognition()
        stream.close()
        # ⭐ IMPORTANT: Broadcast call_ended event
        if beneficiary_id_str in voice_sessions:
            await broadcast_to_call_center({
                "type": "call_ended",
                "beneficiary_id": beneficiary_id_str
            })

            del voice_sessions[beneficiary_id_str]
        print(f"📞 Session closed for beneficiary_id {beneficiary_id_str}")

def serialize_for_json(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return obj
# Add this WebSocket endpoint for the dashboard
@app.websocket("/call-center-ws")
async def call_center_websocket(websocket: WebSocket):
    """WebSocket endpoint for call center dashboard"""
    await websocket.accept()
    call_center_clients.add(websocket)
    print(f"✅ Call center client connected. Total: {len(call_center_clients)}")

    try:
        # Send current active calls
        active_calls_data = []
        for beneficiary_id, session in voice_sessions.items():
            user_info = get_user_by_phone(session["caller_phone"])

            # Serialize user_info safely
            user_name = "Unknown User"
            if user_info and user_info.get("FullName"):
                user_name = user_info["FullName"]

            active_calls_data.append({
                "beneficiary_id": session["beneficiary_id"],
                "caller_phone": session["caller_phone"],
                "call_uuid": session["call_uuid"],
                "session_id": session["session_id"],
                "call_start": session["call_start"].isoformat(),
                "conversation_history": session["conversation_history"],
                "user_info": user_name  # Send just the name string
            })

        await websocket.send_json({
            "type": "initial_state",
            "active_calls": active_calls_data
        })

        print(f"📤 Sent initial_state with {len(active_calls_data)} active calls")

        # Keep connection alive
        while True:
            try:
                # Wait for messages (ping/pong)
                message = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                # Echo back to keep alive
                if message:
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                # Send ping to check if connection is still alive
                try:
                    await websocket.send_json({"type": "ping"})
                except:
                    break

    except WebSocketDisconnect:
        print("📊 Call center client disconnected normally")
    except Exception as e:
        print(f"❌ Call center WebSocket error: {e}")
        traceback.print_exc()
    finally:
        call_center_clients.discard(websocket)
        print(f"📊 Call center client removed. Total: {len(call_center_clients)}")

async def broadcast_to_call_center(message: dict):
    """Broadcast message to all connected call center clients"""
    if not call_center_clients:
        print(f"⚠️ No call center clients connected to receive: {message.get('type')}")
        return

    print(f"📢 Broadcasting {message.get('type')} to {len(call_center_clients)} clients")

    disconnected_clients = set()
    for client in call_center_clients:
        try:
            await client.send_json(message)
        except Exception as e:
            print(f"❌ Failed to send to client: {e}")
            disconnected_clients.add(client)

    # Remove disconnected clients
    for client in disconnected_clients:
        call_center_clients.discard(client)

    if disconnected_clients:
        print(f"🧹 Removed {len(disconnected_clients)} disconnected clients")


# Add this endpoint to serve the dashboard HTML
@app.get("/call-center", response_class=HTMLResponse)
async def call_center_dashboard():
    """Serve the call center dashboard"""
    with open("static/call_center.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())
if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("🌸 Ladki Bahin Yojana - Eligibility Agent API (FastAPI)")
    print("=" * 60)
    print("\nStarting server at http://localhost:8000")
    print("API Documentation: http://localhost:8000/docs")
    print("\nMake sure to set Azure OpenAI credentials in .env file")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000)
