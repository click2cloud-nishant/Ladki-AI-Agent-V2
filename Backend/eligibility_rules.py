# Ladki Bahin Yojana Eligibility Rules Configuration

ELIGIBILITY_RULES = {
    "scheme_name": "मुख्यमंत्री माझी लाडकी बहीण योजना",
    "scheme_name_en": "Mukhyamantri Majhi Ladki Bahin Yojana",
    "monthly_benefit": 1500,
    "proposed_benefit": 2100,
    
    "age": {
        "min": 21,
        "max": 65,
        "message_mr": "वय २१ ते ६५ वर्षे असणे आवश्यक आहे",
        "message_en": "Age must be between 21 and 65 years"
    },
    
    "income": {
        "max_annual": 250000,
        "message_mr": "वार्षिक कौटुंबिक उत्पन्न २.५ लाख रुपयांपेक्षा कमी असावे",
        "message_en": "Annual family income must be less than ₹2.5 lakh"
    },
    
    "gender": {
        "allowed": "female",
        "message_mr": "फक्त महिला अर्जदार पात्र आहेत",
        "message_en": "Only female applicants are eligible"
    },
    
    "residency": {
        "state": "Maharashtra",
        "message_mr": "महाराष्ट्राचे कायमस्वरूपी रहिवासी असणे आवश्यक",
        "message_en": "Must be permanent resident of Maharashtra"
    },
    
    "marital_status": {
        "eligible": ["married", "widowed", "divorced", "abandoned", "unmarried"],
        "unmarried_limit_per_family": 1,
        "message_mr": "विवाहित, विधवा, घटस्फोटित, परित्यक्ता किंवा अविवाहित (कुटुंबात फक्त एक)",
        "message_en": "Married, widowed, divorced, abandoned, or unmarried (only one per family)"
    },
    
    "household_limit": {
        "max_women": 2,
        "message_mr": "एका कुटुंबातून जास्तीत जास्त २ महिला पात्र",
        "message_en": "Maximum 2 women per household can receive benefits"
    },
    
    "bank_account": {
        "required": True,
        "aadhaar_linked": True,
        "dbt_enabled": True,
        "joint_allowed": False,
        "message_mr": "स्वतःचे आधार-लिंक्ड बँक खाते आवश्यक (DBT सक्षम)",
        "message_en": "Own Aadhaar-linked bank account required (DBT enabled)"
    },
    
    "ineligibility_criteria": {
        "income_tax_payer": {
            "check": "family_member_pays_income_tax",
            "message_mr": "कुटुंबातील कोणी आयकर भरत असल्यास अपात्र",
            "message_en": "Ineligible if any family member pays income tax"
        },
        "govt_employee": {
            "check": "family_member_is_govt_employee",
            "message_mr": "कुटुंबातील कोणी सरकारी कर्मचारी असल्यास अपात्र",
            "message_en": "Ineligible if any family member is government employee"
        },
        "govt_pension": {
            "check": "family_member_receives_pension",
            "message_mr": "कुटुंबातील कोणाला सरकारी पेन्शन मिळत असल्यास अपात्र",
            "message_en": "Ineligible if any family member receives government pension"
        },
        "political_position": {
            "check": "family_member_holds_political_position",
            "positions": ["MP", "MLA", "Chairman", "Vice-Chairman", "Director"],
            "message_mr": "कुटुंबातील कोणी खासदार/आमदार/बोर्ड सदस्य असल्यास अपात्र",
            "message_en": "Ineligible if family member is MP/MLA/Board member"
        },
        "four_wheeler": {
            "check": "family_owns_four_wheeler",
            "exemption": "tractor",
            "message_mr": "चारचाकी वाहन असल्यास अपात्र (ट्रॅक्टर वगळता)",
            "message_en": "Ineligible if family owns four-wheeler (tractor exempted)"
        },
        "existing_benefit": {
            "check": "receives_similar_benefit",
            "threshold": 1500,
            "message_mr": "इतर योजनेतून ₹१५०० किंवा अधिक मिळत असल्यास अपात्र",
            "message_en": "Ineligible if already receiving ₹1500+ from another scheme"
        }
    },
    
    "required_documents": [
        {"name": "Aadhaar Card", "name_mr": "आधार कार्ड", "mandatory": True},
        {"name": "Bank Passbook", "name_mr": "बँक पासबुक", "mandatory": True},
        {"name": "Passport Photo", "name_mr": "पासपोर्ट फोटो", "mandatory": True},
        {"name": "Residency Proof", "name_mr": "निवास प्रमाणपत्र", "mandatory": True},
        {"name": "Income Certificate", "name_mr": "उत्पन्न प्रमाणपत्र", "mandatory": False, "condition": "For white ration card holders"},
        {"name": "Ration Card", "name_mr": "रेशन कार्ड", "mandatory": False},
        {"name": "Marriage Certificate", "name_mr": "विवाह प्रमाणपत्र", "mandatory": False, "condition": "If newly married"}
    ],
    
    "official_portal": "ladakibahin.maharashtra.gov.in",
    "ekyc_portal": "ladakibahin.maharashtra.gov.in/ekyc/",
    "helpline": ["181", "1800-120-8040"]
}

# Eligibility check questions for step-by-step guidance
ELIGIBILITY_QUESTIONS = [
    {
        "id": "gender",
        "question_en": "Are you a female applicant?",
        "question_mr": "तुम्ही महिला अर्जदार आहात का?",
        "type": "yes_no",
        "eligible_answer": "yes",
        "fail_message_en": "Sorry, only female applicants are eligible for this scheme.",
        "fail_message_mr": "क्षमस्व, या योजनेसाठी फक्त महिला पात्र आहेत."
    },
    {
        "id": "age",
        "question_en": "What is your age?",
        "question_mr": "तुमचे वय किती आहे?",
        "type": "number",
        "min": 21,
        "max": 65,
        "fail_message_en": "Sorry, your age must be between 21 and 65 years.",
        "fail_message_mr": "क्षमस्व, तुमचे वय २१ ते ६५ वर्षांच्या दरम्यान असणे आवश्यक आहे."
    },
    {
        "id": "residency",
        "question_en": "Are you a permanent resident of Maharashtra?",
        "question_mr": "तुम्ही महाराष्ट्राचे कायमस्वरूपी रहिवासी आहात का?",
        "type": "yes_no",
        "eligible_answer": "yes",
        "fail_message_en": "Sorry, only permanent residents of Maharashtra are eligible.",
        "fail_message_mr": "क्षमस्व, फक्त महाराष्ट्राचे कायमस्वरूपी रहिवासी पात्र आहेत."
    },
    {
        "id": "income",
        "question_en": "Is your annual family income less than ₹2.5 lakh?",
        "question_mr": "तुमचे वार्षिक कौटुंबिक उत्पन्न २.५ लाखांपेक्षा कमी आहे का?",
        "type": "yes_no",
        "eligible_answer": "yes",
        "fail_message_en": "Sorry, annual family income must be less than ₹2.5 lakh.",
        "fail_message_mr": "क्षमस्व, वार्षिक कौटुंबिक उत्पन्न २.५ लाखांपेक्षा कमी असणे आवश्यक आहे."
    },
    {
        "id": "income_tax",
        "question_en": "Does any family member pay income tax?",
        "question_mr": "कुटुंबातील कोणी आयकर भरतो का?",
        "type": "yes_no",
        "eligible_answer": "no",
        "fail_message_en": "Sorry, if any family member pays income tax, you are not eligible.",
        "fail_message_mr": "क्षमस्व, कुटुंबातील कोणी आयकर भरत असल्यास तुम्ही पात्र नाही."
    },
    {
        "id": "govt_employee",
        "question_en": "Is any family member a permanent government employee?",
        "question_mr": "कुटुंबातील कोणी कायमस्वरूपी सरकारी कर्मचारी आहे का?",
        "type": "yes_no",
        "eligible_answer": "no",
        "fail_message_en": "Sorry, families with government employees are not eligible.",
        "fail_message_mr": "क्षमस्व, सरकारी कर्मचारी असलेली कुटुंबे पात्र नाहीत."
    },
    {
        "id": "pension",
        "question_en": "Does any family member receive government pension?",
        "question_mr": "कुटुंबातील कोणाला सरकारी पेन्शन मिळते का?",
        "type": "yes_no",
        "eligible_answer": "no",
        "fail_message_en": "Sorry, families receiving government pension are not eligible.",
        "fail_message_mr": "क्षमस्व, सरकारी पेन्शन मिळणारी कुटुंबे पात्र नाहीत."
    },
    {
        "id": "political",
        "question_en": "Is any family member an MP, MLA, or government board member?",
        "question_mr": "कुटुंबातील कोणी खासदार, आमदार किंवा सरकारी बोर्ड सदस्य आहे का?",
        "type": "yes_no",
        "eligible_answer": "no",
        "fail_message_en": "Sorry, families of political position holders are not eligible.",
        "fail_message_mr": "क्षमस्व, राजकीय पदाधिकाऱ्यांची कुटुंबे पात्र नाहीत."
    },
    {
        "id": "four_wheeler",
        "question_en": "Does your family own a four-wheeler vehicle (car/SUV)? (Tractor is exempted)",
        "question_mr": "तुमच्या कुटुंबाकडे चारचाकी वाहन (कार/SUV) आहे का? (ट्रॅक्टर वगळता)",
        "type": "yes_no",
        "eligible_answer": "no",
        "fail_message_en": "Sorry, families owning four-wheeler vehicles are not eligible.",
        "fail_message_mr": "क्षमस्व, चारचाकी वाहन असलेली कुटुंबे पात्र नाहीत."
    },
    {
        "id": "bank_account",
        "question_en": "Do you have your own Aadhaar-linked bank account?",
        "question_mr": "तुमचे स्वतःचे आधार-लिंक्ड बँक खाते आहे का?",
        "type": "yes_no",
        "eligible_answer": "yes",
        "fail_message_en": "You need an Aadhaar-linked bank account to receive benefits.",
        "fail_message_mr": "लाभ मिळण्यासाठी आधार-लिंक्ड बँक खाते आवश्यक आहे."
    }
]
