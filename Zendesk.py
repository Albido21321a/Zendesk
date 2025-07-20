import requests
import os
import json
import time
import threading
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import messagebox as mb
from tkinter import ttk

from customtkinter import (
    CTk,
    CTkButton,
    CTkEntry,
    CTkFrame,
    CTkLabel,
    CTkOptionMenu,
    CTkCheckBox,
    CTkSwitch,
    CTkTextbox,
    CTkToplevel,
)

# 🔐 Replace this with your actual OpenRouter API key
OPENROUTER_API_KEY = "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"

# Initialize app
app = CTk()
app.title("Zendesk Scheduler with AI")
app.geometry("960x900")

frame = CTkFrame(app)
frame.pack(padx=20, pady=20, fill="both", expand=True)

# Entry fields
email_entry = CTkEntry(frame, width=600, placeholder_text="Zendesk Email")
email_entry.pack(pady=5)
password_entry = CTkEntry(frame, width=600, placeholder_text="Zendesk Password", show="*")
password_entry.pack(pady=5)
ticket_entry = CTkEntry(frame, width=600, placeholder_text="Ticket ID")
ticket_entry.pack(pady=5)
message_box = CTkTextbox(frame, width=800, height=200)
message_box.pack(pady=10)

# 🧠 AI Integration
ai_frame = CTkFrame(frame)
ai_frame.pack(pady=(10, 5))

def call_openrouter(prompt):
    try:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "HTTP-Referer": "https://your-app-url.com",
            "X-Title": "Zendesk Scheduler AI",
        }

        data = {
            "model": "openai/gpt-3.5-turbo",
            "messages": [{"role": "user", "content": prompt}],
        }

        res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data)

        if res.status_code == 200:
            return res.json()["choices"][0]["message"]["content"].strip()
        else:
            return f"❌ Error: {res.text}"

    except Exception as e:
        return f"⚠️ Exception: {str(e)}"

def get_last_comment(email, password, ticket_id):
    # Replace with actual Zendesk API call
    return f"Sample last message from ticket {ticket_id}."

def generate_ai_reply(ticket_id, email, password):
    last_comment = get_last_comment(email, password, ticket_id)
    if not last_comment:
        return "⚠️ No last comment found for this ticket."
    prompt = f"You are a helpful support agent. Write a polite, concise reply to this customer message:\n\n{last_comment}\n\nReply:"
    return call_openrouter(prompt)

def summarize_last_comment(ticket_id, email, password):
    last_comment = get_last_comment(email, password, ticket_id)
    if not last_comment:
        return "⚠️ No last comment to summarize."

    prompt = (
        "You are a skilled customer support assistant. Carefully read the following customer message "
        "and write a detailed yet concise summary capturing the main problem, requests, or questions, "
        "without mentioning ticket numbers or generic phrases. Use complete sentences and be informative.\n\n"
        f"Customer Message:\n{last_comment}\n\nSummary:"
    )

    return call_openrouter(prompt)



def on_generate_ai():
    email = email_entry.get().strip()
    password = password_entry.get().strip()
    ticket = ticket_entry.get().strip()

    if not (email and password and ticket):
        mb.showerror("Missing Info", "Please fill Zendesk email, password, and ticket ID.")
        return

    message_box.delete("1.0", tk.END)
    message_box.insert("1.0", "⏳ Generating reply...")

    def worker():
        reply = generate_ai_reply(ticket, email, password)
        message_box.delete("1.0", tk.END)
        message_box.insert("1.0", reply)

    threading.Thread(target=worker).start()

def on_summarize():
    email = email_entry.get().strip()
    password = password_entry.get().strip()
    ticket = ticket_entry.get().strip()

    if not (email and password and ticket):
        mb.showerror("Missing Info", "Please fill Zendesk email, password, and ticket ID.")
        return

    message_box.delete("1.0", tk.END)
    message_box.insert("1.0", "⏳ Summarizing...")

    def worker():
        summary = summarize_last_comment(ticket, email, password)
        message_box.delete("1.0", tk.END)
        message_box.insert("1.0", summary)

    threading.Thread(target=worker).start()

CTkButton(ai_frame, text="🧠 Generate AI Reply", command=on_generate_ai).pack(side=tk.LEFT, padx=5)
CTkButton(ai_frame, text="📄 Summarize Comment", command=on_summarize).pack(side=tk.LEFT, padx=5)

app.mainloop()
