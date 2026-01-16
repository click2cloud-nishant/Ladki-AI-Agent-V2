import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import os
import pandas as pd
from dotenv import load_dotenv
from openai import AzureOpenAI
import json
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("Agg")
from azure.storage.blob import BlobServiceClient
import uuid
from datetime import datetime
from dateutil.relativedelta import relativedelta
from azure.storage.blob import generate_blob_sas, BlobSasPermissions
from datetime import timedelta

from database import (
    get_beneficiary_by_aadhaar_last4,
    get_beneficiary_details,
    get_beneficiary_transactions
)
# --------------------------------------------------
# Load ENV
# --------------------------------------------------
load_dotenv()

# --------------------------------------------------
# Azure OpenAI
# --------------------------------------------------
AZURE_CLIENT = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
)
AZURE_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")

# --------------------------------------------------
# Azure Storage
# --------------------------------------------------
AZURE_SA_NAME = os.getenv("AZURE_SA_NAME")
AZURE_SA_ACCESSKEY = os.getenv("AZURE_SA_ACCESSKEY")

# --------------------------------------------------
# Month Map
# --------------------------------------------------
MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12
}

# --------------------------------------------------
# FastAPI App
# --------------------------------------------------
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------
# Session Memory
# --------------------------------------------------
SESSION_HISTORY = {}

# --------------------------------------------------
# Request Schema
# --------------------------------------------------
class ChatRequest(BaseModel):
    message: str
    aadhaar_last4: Optional[str] = None
    session_id: str

# --------------------------------------------------
# LLM Chat
# --------------------------------------------------
def call_llm(prompt: str) -> str:
    system_prompt = (
        "You are a Ladli Behna Yojana assistant.\n"
        "Rules:\n"
        "- Answer ONLY what is explicitly asked\n"
        "- Be concise and precise\n"
        "- Do NOT add extra details unless requested\n"

        "- If the user asks whether a specific document (bank account, mobile number, or Aadhaar) "
        "is linked, seeded, updated, or verified correctly AND the user has NOT yet provided "
        "that document value, you MUST ask ONLY for that same document\n"

        "- HOWEVER, if the user HAS provided the document value in the conversation "
        "or in the current message, AND the database context contains the corresponding value, "
        "you MUST compare the user-provided value with the database value\n"

        "- If both values match, clearly confirm that it is linked correctly\n"
        "- If they do not match, clearly state that it is not linked correctly\n"

        "- Never ask again for the document once it has been provided\n"
        "- Never ask for Aadhaar when the question is about bank account or mobile number\n"
        "- Do NOT ask for last 4 digits or partial identifiers\n"
    )

    response = AZURE_CLIENT.chat.completions.create(
        model=AZURE_DEPLOYMENT,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        max_tokens=800
    )

    return response.choices[0].message.content.strip()

# --------------------------------------------------
# LLM Intent Extraction
# --------------------------------------------------
def extract_transaction_intent_llm(user_prompt: str):
    intent_prompt = f"""
Extract transaction intent from the user message.

Rules:
- transaction_flag = 1 only if the user asks about payments or transactions
- If user says "last N months", set last_n_months = N
- If user mentions individual months, use month_list
- If user mentions a range like "June to September", use start_month and end_month
- ONLY ONE of (month_list) OR (start/end) OR (last_n_months) can be non-null
- Month names must be lowercase full names
- Return STRICT JSON only

User message:
"{user_prompt}"

JSON:
{{
  "transaction_flag": 0 or 1,
  "month_list": ["june","july"] or null,
  "start_month": "june" or null,
  "end_month": "september" or null,
  "last_n_months": number or null
}}
"""
    response = AZURE_CLIENT.chat.completions.create(
        model=AZURE_DEPLOYMENT,
        messages=[
            {"role": "system", "content": "Return valid JSON only."},
            {"role": "user", "content": intent_prompt}
        ],
        temperature=0,
        max_tokens=200
    )
    return json.loads(response.choices[0].message.content)

# --------------------------------------------------
# Upload Chart to Azure Blob
# --------------------------------------------------
def upload_chart(df: pd.DataFrame):
    print("Generating chart...")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.figure(figsize=(10, 5))
    plt.bar(df["PaymentMonth"], df["Amount"])
    plt.xticks(rotation=45)
    plt.xlabel("Month")
    plt.ylabel("Amount")
    plt.title("Transaction History")
    plt.tight_layout()

    file_name = f"transactions_{uuid.uuid4()}.png"
    plt.savefig(file_name)
    plt.close()

    blob_service = BlobServiceClient(
        account_url=f"https://{AZURE_SA_NAME}.blob.core.windows.net",
        credential=AZURE_SA_ACCESSKEY
    )

    container_name = "charts"
    container_client = blob_service.get_container_client(container_name)

    # Ensure container exists
    try:
        container_client.create_container()
    except Exception:
        pass

    blob_client = container_client.get_blob_client(file_name)

    with open(file_name, "rb") as data:
        blob_client.upload_blob(data, overwrite=True)

    os.remove(file_name)

    #  Generate SAS URL (READ access for 1 hour)
    sas_token = generate_blob_sas(
        account_name=AZURE_SA_NAME,
        container_name=container_name,
        blob_name=file_name,
        account_key=AZURE_SA_ACCESSKEY,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.utcnow() + timedelta(hours=1000)
    )

    sas_url = f"https://{AZURE_SA_NAME}.blob.core.windows.net/{container_name}/{file_name}?{sas_token}"

    return sas_url


# --------------------------------------------------
# Chat API
# --------------------------------------------------
@app.post("/post-application-chat")
def post_chat(req: ChatRequest):
    session_id = req.session_id
    user_message = req.message
    aadhaar_last4 = req.aadhaar_last4

    if session_id not in SESSION_HISTORY:
        SESSION_HISTORY[session_id] = []

    db_context = ""
    chart_url = None

    if aadhaar_last4:
        beneficiary_id = get_beneficiary_by_aadhaar_last4(aadhaar_last4)
        if not beneficiary_id:
            return {"response": "No records found", "history": SESSION_HISTORY[session_id]}

        print(f"Found BeneficiaryId: {beneficiary_id}")

        beneficiary = get_beneficiary_details(beneficiary_id)
        print("Beneficiary Details:", beneficiary)
        transactions = get_beneficiary_transactions(beneficiary_id)
        
        transc_df = pd.DataFrame(transactions)
        # print("Transactions DF:", transc_df)
        transc_df["TransactionDate"] = pd.to_datetime(transc_df["TransactionDate"])

        intent = extract_transaction_intent_llm(user_message)

        if intent["transaction_flag"] == 1:

            if intent["last_n_months"]:
                end_date = datetime.today()
                start_date = end_date - relativedelta(months=intent["last_n_months"])
                transc_df = transc_df[
                    (transc_df["TransactionDate"] >= start_date) &
                    (transc_df["TransactionDate"] <= end_date)
                ]

            elif intent["start_month"] and intent["end_month"]:
                sm = MONTH_MAP[intent["start_month"]]
                em = MONTH_MAP[intent["end_month"]]
                transc_df["TxnMonth"] = transc_df["TransactionDate"].dt.month
                transc_df = transc_df[
                    (transc_df["TxnMonth"] >= sm) &
                    (transc_df["TxnMonth"] <= em)
                ]

            elif intent["month_list"]:
                months = [MONTH_MAP[m] for m in intent["month_list"]]
                transc_df["TxnMonth"] = transc_df["TransactionDate"].dt.month
                transc_df = transc_df[transc_df["TxnMonth"].isin(months)]

            chart_url = upload_chart(transc_df)

        db_context = f"""
Beneficiary:
{beneficiary}

Transactions:
{transc_df.to_dict(orient="records")}
"""
        
    last_5_history = SESSION_HISTORY[session_id][-5:]

    prompt = f"""
Conversation history:
{last_5_history}

Database data:
{db_context}

User question:
{user_message}
"""

    bot_reply = call_llm(prompt)

    SESSION_HISTORY[session_id].append({
        "user": user_message,
        "bot": bot_reply
    })

    return {
        "response": bot_reply,
        "transaction_chart_url": chart_url,
        "history": SESSION_HISTORY[session_id][-5:]
    }

