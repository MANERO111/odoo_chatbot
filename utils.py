# utils.py
import os
import requests
import json

user_states = {}

def set_state(sender, step, **kwargs):
    """Update or initialize conversation state for a specific user."""
    if sender not in user_states:
        user_states[sender] = {}
    user_states[sender]["step"] = step
    for key, value in kwargs.items():
        user_states[sender][key] = value

def get_state(sender):
    """Retrieve the current state dictionary for a user."""
    return user_states.get(sender, {})

def clear_state(sender):
    """Clear user conversation state, effectively restarting the flow."""
    if sender in user_states:
        del user_states[sender]

def generate_choice_message(products):
    """
    Format ambiguous product options for WhatsApp.
    """
    msg = "Lqina bzzaf dyal l-moumtajat kitchabho ldakchi li tlbti. Afak jawb b rqm dyal l-moumtaj li bghiti:\n"
    for i, p in enumerate(products):
        msg += f"{i+1}. {p['name']} (Tman: {p.get('price', 'N/A')} Dh)\n"
    return msg

def generate_company_choice_message(companies):
    """
    Format the list of companies as a numbered choice message.
    """
    msg = "Lqina bzzaf dyal l-companies. Afak khtar rqm dyal l-company li bghiti:\n"
    for i, c in enumerate(companies):
        msg += f"{i+1}. {c['name']}\n"
    return msg

def extract_meta_whatsapp_data(data):
    """
    Extract sender and body from Meta WhatsApp Cloud API webhook JSON.
    """
    try:
        if 'entry' in data:
            for entry in data['entry']:
                for change in entry.get('changes', []):
                    value = change.get('value', {})
                    if 'messages' in value:
                        for message in value['messages']:
                            if 'text' in message:
                                return message['text']['body'], message['from']
    except Exception as e:
        print(f"[Meta Parsing Error] {e}")
    return None, None

def send_whatsapp_message(to_phone, body):
    """
    Send a message via Meta WhatsApp Cloud API.
    """
    if os.environ.get("SIMULATION_MODE") == "true":
        print(f"\n>>> [BOT REPLY TO {to_phone}]: {body}\n")
        return {"status": "simulated"}

    access_token = os.environ.get("META_ACCESS_TOKEN")
    phone_number_id = os.environ.get("META_PHONE_NUMBER_ID")
    
    url = f"https://graph.facebook.com/v21.0/{phone_number_id}/messages"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": body}
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"[Meta Send Error] {e}")
        if hasattr(e, 'response') and e.response:
            print(f"Response: {e.response.text}")
        return None
