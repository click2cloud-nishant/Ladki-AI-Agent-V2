# utils.py
import io
import re
import pytesseract
from PIL import Image
from pdf2image import convert_from_bytes
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import APIRouter, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from pathlib import Path
import json
import os
from openai import AzureOpenAI


from database import db_manager

# ============== Azure OpenAI Setup ==============
try:
    openai_client = AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
    )
    AZURE_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    print("✅ Azure OpenAI client initialized for Aadhaar parsing")
except Exception as e:
    openai_client = None
    AZURE_DEPLOYMENT = None
    print(f"⚠️ Azure OpenAI not available: {e}")

# ============== Router Setup ==============
router = APIRouter(prefix="/api", tags=["Aadhaar"])

# In-memory session storage (use Redis in production)
sessions = {}

def detect_language(text: str) -> str:

    if not openai_client:
        # Fallback to simple detection
        if re.search(r'[\u0900-\u097F]', text):  # Devanagari script
            if any(word in text for word in ['आहे', 'का', 'मी', 'तुम्ही', 'आपण']):
                return "marathi"
            return "hindi"
        return "english"
    
    try:
        response = openai_client.chat.completions.create(
            model=AZURE_DEPLOYMENT,
            messages=[
                {
                    "role": "system",
                    "content": "You are a language detector. Detect if the text is in Marathi, Hindi, or English. Return ONLY one word: 'marathi', 'hindi', or 'english'."
                },
                {
                    "role": "user",
                    "content": f"Detect language: {text}"
                }
            ],
            temperature=0,
            max_tokens=10
        )
        
        detected = response.choices[0].message.content.strip().lower()
        if detected in ["marathi", "hindi", "english"]:
            return detected
        return "english"  # Default fallback
        
    except Exception as e:
        print(f"⚠️ Language detection failed: {e}")
        return "english"


def get_aadhaar_request_message(language: str) -> str:
    """
    Get Aadhaar request message in the specified language.
    
    Args:
        language: "marathi", "hindi", or "english"
    
    Returns:
        Localized message string
    """
    messages = {
        "marathi": (
            "🙏 नमस्कार!\n\n"
            "पात्रता तपासण्यासाठी, कृपया तुमचे आधार कार्ड अपलोड करा किंवा आधार क्रमांक प्रविष्ट करा."
        ),
        "hindi": (
            "🙏 नमस्कार!\n\n"
            "पात्रता जांचने के लिए, कृपया अपना आधार कार्ड अपलोड करें या आधार नंबर दर्ज करें."
        ),
        "english": (
            "🙏 Hello!\n\n"
            "To check eligibility, please upload your Aadhaar card or enter your Aadhaar number."
        )
    }
    
    return messages.get(language, messages["english"])


def get_aadhaar_not_found_message(language: str) -> str:
    """Get 'Aadhaar not found' message in the specified language."""
    messages = {
        "marathi": "❌ आपला आधार क्रमांक डेटाबेसमध्ये सापडला नाही.\n\n📤 कृपया आपले आधार कार्ड अपलोड करा:\n• आधी समोरचा भाग अपलोड करा\n• नंतर मागचा भाग अपलोड करा",
        "hindi": "❌ आपका आधार नंबर डेटाबेस में नहीं मिला।\n\n📤 कृपया अपना आधार कार्ड अपलोड करें:\n• पहले आगे का भाग अपलोड करें\n• फिर पीछे का भाग अपलोड करें",
        "english": "❌ Your Aadhaar number was not found in the database.\n\n📤 Please upload your Aadhaar card:\n• First upload the front side\n• Then upload the back side"
    }
    return messages.get(language, messages["english"])


def get_front_processed_message(language: str, extracted_data: dict) -> str:
    """Get 'front side processed' message in the specified language."""
    messages = {
        "marathi": f"✅ आधारचा समोरचा भाग यशस्वीरित्या प्रक्रिया झाली!\n\n📋 काढलेली माहिती:\n• नाव: {extracted_data.get('FullName') or 'सापडले नाही'}\n• आधार क्रमांक: {extracted_data.get('AadhaarNo') or 'सापडले नाही'}\n• जन्मतारीख: {extracted_data.get('DateOfBirth') or 'सापडले नाही'}\n• लिंग: {extracted_data.get('Gender') or 'सापडले नाही'}\n\n📤 आता कृपया मागचा भाग अपलोड करा.",
        "hindi": f"✅ आधार का अगला भाग सफलतापूर्वक प्रोसेस हुआ!\n\n📋 निकाली गई जानकारी:\n• नाम: {extracted_data.get('FullName') or 'नहीं मिला'}\n• आधार नंबर: {extracted_data.get('AadhaarNo') or 'नहीं मिला'}\n• जन्म तिथि: {extracted_data.get('DateOfBirth') or 'नहीं मिला'}\n• लिंग: {extracted_data.get('Gender') or 'नहीं मिला'}\n\n📤 अब कृपया पिछला भाग अपलोड करें.",
        "english": f"✅ Aadhaar front side successfully processed!\n\n📋 Extracted Information:\n• Name: {extracted_data.get('FullName') or 'Not found'}\n• Aadhaar Number: {extracted_data.get('AadhaarNo') or 'Not found'}\n• Date of Birth: {extracted_data.get('DateOfBirth') or 'Not found'}\n• Gender: {extracted_data.get('Gender') or 'Not found'}\n\n📤 Now please upload the back side."
    }
    return messages.get(language, messages["english"])


def get_back_processed_message(language: str, both_complete: bool = False) -> str:
    """Get 'back side processed' message in the specified language."""
    if both_complete:
        messages = {
            "marathi": "✅ आधार कार्डच्या दोन्ही बाजू यशस्वीरित्या प्रक्रिया झाल्या आहेत. डेटा सेव्ह झाला आहे.",
            "hindi": "✅ आधार कार्ड की दोनों साइड सफलतापूर्वक प्रोसेस हो गई। डेटा सेव हो गया है।",
            "english": "✅ Both sides of Aadhaar card successfully processed. Data has been saved."
        }
    else:
        messages = {
            "marathi": "✅ मागचा भाग प्रक्रिया झाला. कृपया आता समोरचा भाग अपलोड करा.",
            "hindi": "✅ पिछला भाग प्रोसेस हो गया। कृपया अब अगला भाग अपलोड करें।",
            "english": "✅ Back side processed. Please now upload the front side."
        }
    return messages.get(language, messages["english"])


def get_image_error_message(language: str) -> str:
    """Get image processing error message in the specified language."""
    messages = {
        "marathi": "❌ प्रतिमेतून मजकूर वाचला जाऊ शकला नाही. कृपया स्पष्ट प्रतिमा अपलोड करा.",
        "hindi": "❌ छवि से टेक्स्ट नहीं पढ़ा जा सका। कृपया साफ छवि अपलोड करें।",
        "english": "❌ Could not read text from image. Please upload a clear image."
    }
    return messages.get(language, messages["english"])


def get_side_detection_error_message(language: str) -> str:
    """Get side detection error message in the specified language."""
    messages = {
        "marathi": "❌ आधार कार्ड ओळखले जाऊ शकले नाही. कृपया स्पष्ट प्रतिमा अपलोड करा.",
        "hindi": "❌ आधार कार्ड की पहचान नहीं हो सकी। कृपया स्पष्ट छवि अपलोड करें।",
        "english": "❌ Could not identify Aadhaar card. Please upload a clear image."
    }
    return messages.get(language, messages["english"])

# ============== OCR & Extraction Functions ==============

def extract_text_from_bytes(file_bytes: bytes, extension: str) -> str:
    try:
        if extension.lower() == ".pdf":
            images = convert_from_bytes(file_bytes, dpi=300)
            return "\n".join(
                pytesseract.image_to_string(img, lang="eng+hin")
                for img in images
            )
        else:
            img = Image.open(io.BytesIO(file_bytes))
            return pytesseract.image_to_string(img, lang="eng+hin")
    except Exception as e:
        print(f"Error extracting text: {e}")
        return ""


def detect_aadhaar_side(text: str) -> str:

    # Front side typically has the 12-digit Aadhaar number prominently
    if re.search(r'\b\d{4}\s?\d{4}\s?\d{4}\b', text):
        return "front"
    
    # Back side has address information
    if re.search(r'Address|पत्ता|पता', text, re.IGNORECASE):
        return "back"
    
    return "unknown"


def parse_with_ai(text: str, document_side: str) -> Dict[str, Any]:
    if not openai_client:
        print("⚠️ Azure OpenAI not configured. Using basic extraction.")
        return None
    
    if document_side == "front":
        prompt = f"""Extract information from this Aadhaar card FRONT side OCR text.

Return ONLY a JSON object with these exact fields:
- aadhaar_number: 12 digits (remove all spaces)
- full_name: Complete name in English
- date_of_birth: In DD/MM/YYYY format
- gender: Either "Male" or "Female"

OCR Text:
{text}

Return ONLY valid JSON, no markdown, no explanation."""

    else:  # back side
        prompt = f"""Extract information from this Aadhaar card BACK side OCR text.

Return ONLY a JSON object with these exact fields:
- address: Complete address
- pincode: 6-digit postal code
- state: State name in English

OCR Text:
{text}

Return ONLY valid JSON, no markdown, no explanation."""

    try:
        response = openai_client.chat.completions.create(
            model=AZURE_DEPLOYMENT,
            messages=[
                {"role": "system", "content": "You are an expert at extracting structured data from Aadhaar cards. Return only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            max_tokens=500
        )
        
        result = response.choices[0].message.content.strip()
        
        # Remove markdown code blocks if present
        result = result.replace("```json", "").replace("```", "").strip()
        
        parsed = json.loads(result)
        print(f"✅ AI successfully parsed {document_side} side")
        return parsed
        
    except Exception as e:
        print(f"⚠️ AI parsing failed: {e}")
        return None


def extract_aadhaar_front_details(ocr_text: str) -> Dict[str, Any]:
    # Try AI parsing first
    ai_result = parse_with_ai(ocr_text, "front")
    
    if ai_result:
        # Convert AI result to expected format
        data = {
            "AadhaarNo": ai_result.get("aadhaar_number"),
            "FullName": ai_result.get("full_name"),
            "DateOfBirth": None,
            "Gender": ai_result.get("gender")
        }
        
        # Parse date from AI result
        dob_str = ai_result.get("date_of_birth")
        if dob_str:
            try:
                data["DateOfBirth"] = datetime.strptime(dob_str, "%d/%m/%Y").date()
            except ValueError:
                pass
        
        return data
    
    # Fallback to regex-based extraction
    data = {
        "AadhaarNo": None,
        "FullName": None,
        "DateOfBirth": None,
        "Gender": None
    }

    # Extract 12-digit Aadhaar number
    aadhaar = re.search(r'\b\d{4}\s?\d{4}\s?\d{4}\b', ocr_text)
    if aadhaar:
        data["AadhaarNo"] = aadhaar.group().replace(" ", "")

    # Extract name (assumes "Name:" or "नाम:" label)
    name = re.search(r'(?:Name|नाम)[:\s]+([A-Za-z\s]+)', ocr_text, re.IGNORECASE)
    if name:
        data["FullName"] = name.group(1).strip()

    # Extract date of birth (DD/MM/YYYY format)
    dob = re.search(r'\b\d{2}/\d{2}/\d{4}\b', ocr_text)
    if dob:
        try:
            data["DateOfBirth"] = datetime.strptime(dob.group(), "%d/%m/%Y").date()
        except ValueError:
            data["DateOfBirth"] = None

    # Extract gender
    if re.search(r'\b(?:Female|महिला)\b', ocr_text, re.IGNORECASE):
        data["Gender"] = "Female"
    elif re.search(r'\b(?:Male|पुरुष)\b', ocr_text, re.IGNORECASE):
        data["Gender"] = "Male"

    return data


def extract_aadhaar_back_details(ocr_text: str) -> Dict[str, Any]:

    # Try AI parsing first
    ai_result = parse_with_ai(ocr_text, "back")
    
    if ai_result:
        return {
            "Address": ai_result.get("address"),
            "Pincode": ai_result.get("pincode"),
            "State": ai_result.get("state"),
            "Country": "India"
        }
    
    # Fallback to regex-based extraction
    data = {
        "Address": None,
        "Pincode": None,
        "State": None,
        "Country": "India"
    }

    # Extract 6-digit pincode
    pin = re.search(r'\b\d{6}\b', ocr_text)
    if pin:
        data["Pincode"] = pin.group()

    # Extract address (look for text after "Address:" label)
    address = re.search(r'(?:Address|पत्ता|पता)[:\s]+([\s\S]{30,200})', ocr_text, re.IGNORECASE)
    if address:
        addr = re.sub(r'\s+', ' ', address.group(1)).strip()
        data["Address"] = addr
        
        # Try to detect state from address
        if re.search(r'Maharashtra|महाराष्ट्र', addr, re.IGNORECASE):
            data["State"] = "Maharashtra"
        elif re.search(r'Karnataka|कर्नाटक', addr, re.IGNORECASE):
            data["State"] = "Karnataka"
        elif re.search(r'Tamil Nadu|तमिलनाडु', addr, re.IGNORECASE):
            data["State"] = "Tamil Nadu"
        # Add more states as needed

    return data


def validate_aadhaar_number(aadhaar_number: str) -> bool:

    return bool(re.fullmatch(r'\d{12}', aadhaar_number))


def merge_aadhaar(front: Dict[str, Any], back: Dict[str, Any]) -> Dict[str, Any]:

    # Convert date object to string if it exists
    dob = front.get("DateOfBirth")
    if dob and hasattr(dob, 'isoformat'):
        dob = dob.isoformat()  # Converts date to 'YYYY-MM-DD' string
    
    return {
        "aadhaar_number": front.get("AadhaarNo"),
        "full_name": front.get("FullName"),
        "date_of_birth": dob,
        "gender": front.get("Gender"),
        "address": back.get("Address"),
        "pincode": back.get("Pincode"),
        "district": back.get("State"),
        "country": back.get("Country", "India")
    }


def clean_text(text: str) -> str:
    return bool(re.fullmatch(r'\d{12}', aadhaar_number))


def clean_text(text: str) -> str:

    # Remove multiple spaces
    text = re.sub(r'\s+', ' ', text)
    # Remove special characters but keep necessary punctuation
    text = re.sub(r'[^\w\s\/:,.-]', '', text)
    return text.strip()


# ============== Helper Functions ==============

def initialize_session(session_id: str):
    """Initialize session state for Aadhaar processing"""
    if session_id not in sessions:
        sessions[session_id] = {
            "aadhaar": {
                "front": None,
                "back": None,
                "merged": None,
                "source": None,
                "saved": False
            },
            "beneficiary_id": None
        }
    return sessions[session_id]


# ============== API Endpoint ==============

@router.post("/aadhaar-details")
async def aadhaar_details(
    message: str = Form(...),
    session_id: str = Form(...),
    prev_res: Optional[str] = Form(None),
    aadhaar_last4: Optional[str] = Form(None),
    doc_type: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    prev_res_mode: str = Form("eligibility")
):
    try:
        # Initialize session
        session = initialize_session(session_id)
        aadhaar_state = session["aadhaar"]
        
        response_data = {
            "success": False,
            "message": "",
            "data": None,
            "mode": prev_res_mode,
            "side_detected": None,
            "both_sides_complete": False,
            "beneficiary_id": session.get("beneficiary_id")
        }
        
        # -------- OPTION A: Aadhaar Number Verification --------
        aadhaar_match = re.fullmatch(r"\d{12}", message.strip())
        if aadhaar_match:
            aadhaar_no = aadhaar_match.group()
            
            # Validate Aadhaar number
            if not validate_aadhaar_number(aadhaar_no):
                response_data["success"] = False
                response_data["message"] = "Invalid Aadhaar number format. Must be 12 digits."
                return JSONResponse(content=response_data, status_code=400)
            
            # Check if Aadhaar exists in database
            data = db_manager.get_aadhaar_details(aadhaar_no)
            
            if data:
                # Update session with found data
                aadhaar_state.update({
                    "source": "number",
                    "merged": {
                        "aadhaar_number": data["AadhaarNo"],
                        "full_name": data["FullName"],
                        "date_of_birth": str(data["DateOfBirth"]),
                        "gender": data["Gender"],
                        "address": data["Address"],
                        "district": data["State"],
                        "pincode": data.get("Pincode")
                    },
                    "saved": True
                })
                
                response_data.update({
                    "success": True,
                    "message": "आधार सत्यापित हो गया है। आपकी जानकारी मिल गई है।",
                    "data": aadhaar_state["merged"],
                    "both_sides_complete": True
                })
                
                return JSONResponse(content=response_data)
            else:
                response_data.update({
                    "success": False,
                    "message": "आधार नंबर डेटाबेस में नहीं मिला। कृपया अपना आधार कार्ड अपलोड करें।"
                })
                return JSONResponse(content=response_data, status_code=404)
        
        # -------- OPTION B: Aadhaar Card Upload --------
        if file and doc_type == "aadhaar" and aadhaar_state["source"] != "number":
            # Validate file type
            allowed_extensions = {".jpg", ".jpeg", ".png", ".pdf"}
            file_extension = Path(file.filename).suffix.lower()
            
            if file_extension not in allowed_extensions:
                response_data.update({
                    "success": False,
                    "message": f"अमान्य फ़ाइल प्रकार। केवल {', '.join(allowed_extensions)} अपलोड करें।"
                })
                return JSONResponse(content=response_data, status_code=400)
            
            # Read file
            file_bytes = await file.read()
            
            # Extract text using OCR
            ocr_text = extract_text_from_bytes(file_bytes, file_extension)
            
            if not ocr_text.strip():
                response_data.update({
                    "success": False,
                    "message": "छवि से टेक्स्ट नहीं निकाला जा सका। कृपया स्पष्ट छवि अपलोड करें।"
                })
                return JSONResponse(content=response_data, status_code=400)
            
            # Detect side (front or back)
            side = detect_aadhaar_side(ocr_text)
            
            if side == "unknown":
                response_data.update({
                    "success": False,
                    "message": "आधार कार्ड की साइड पहचान नहीं हो सकी। कृपया स्पष्ट छवि अपलोड करें।"
                })
                return JSONResponse(content=response_data, status_code=400)
            
            # Set source as upload
            aadhaar_state["source"] = "upload"
            
            # Extract details based on detected side
            if side == "front":
                extracted_data = extract_aadhaar_front_details(ocr_text)
                aadhaar_state["front"] = extracted_data
                
                # Convert date to string for JSON serialization
                if extracted_data.get("DateOfBirth") and hasattr(extracted_data["DateOfBirth"], 'isoformat'):
                    extracted_data["DateOfBirth"] = extracted_data["DateOfBirth"].isoformat()
                
                response_data.update({
                    "success": True,
                    "message": "आधार का अगला भाग प्रोसेस हो गया। कृपया पिछला भाग अपलोड करें।",
                    "data": extracted_data,
                    "side_detected": "front",
                    "both_sides_complete": False
                })
                
            elif side == "back":
                extracted_data = extract_aadhaar_back_details(ocr_text)
                aadhaar_state["back"] = extracted_data
                
                # Check if both sides are now available
                if aadhaar_state["front"] and aadhaar_state["back"]:
                    # Merge data from both sides
                    merged_data = merge_aadhaar(
                        aadhaar_state["front"],
                        aadhaar_state["back"]
                    )
                    aadhaar_state["merged"] = merged_data
                    
                    # Save to database if not already saved
                    if not aadhaar_state["saved"]:
                        beneficiary_id = db_manager.save_beneficiary_from_aadhaar(merged_data)
                        aadhaar_state["saved"] = True
                        session["beneficiary_id"] = beneficiary_id
                        response_data["beneficiary_id"] = beneficiary_id
                    
                    response_data.update({
                        "success": True,
                        "message": "आधार कार्ड की दोनों साइड सफलतापूर्वक प्रोसेस हो गई। डेटा सेव हो गया है।",
                        "data": merged_data,
                        "side_detected": "back",
                        "both_sides_complete": True
                    })
                else:
                    response_data.update({
                        "success": True,
                        "message": "पिछला भाग प्रोसेस हो गया। कृपया अगला भाग अपलोड करें।",
                        "data": extracted_data,
                        "side_detected": "back",
                        "both_sides_complete": False
                    })
            
            return JSONResponse(content=response_data)
        
        # -------- No Aadhaar Processing Needed --------
        # If message doesn't contain Aadhaar number and no file uploaded
        if not aadhaar_match and not (file and doc_type == "aadhaar"):
            # Check current status
            if aadhaar_state["merged"]:
                response_data.update({
                    "success": True,
                    "message": "आधार पहले से सत्यापित है।",
                    "data": aadhaar_state["merged"],
                    "both_sides_complete": True
                })
            else:
                response_data.update({
                    "success": False,
                    "message": "कृपया अपना 12 अंकों का आधार नंबर दर्ज करें या आधार कार्ड अपलोड करें।"
                })
            
            return JSONResponse(content=response_data)
            
    except HTTPException as he:
        raise he
    except Exception as e:
        return JSONResponse(
            content={
                "success": False,
                "message": f"त्रुटि: {str(e)}",
                "data": None,
                "mode": prev_res_mode
            },
            status_code=500
        )