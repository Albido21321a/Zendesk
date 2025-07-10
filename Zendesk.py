from customtkinter import *
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import tkinter.messagebox as mb
import tkinter as tk
import threading
import time
import re
import requests
import json
import os
from bs4 import BeautifulSoup

# Global tracker of scheduled times
scheduled_queue_times = []
def schedule_all_jobs():
    if not job_queue:
        mb.showinfo("Queue Empty", "There are no jobs in the queue to schedule.")
        return

    interval_text = interval_option.get()
    interval_minutes = 15 if "15" in interval_text else 30
    now = datetime.now().replace(second=0, microsecond=0)

    # ✅ Use scheduled_queue_times to avoid overlap
    future_times = [t for t in scheduled_queue_times if isinstance(t, datetime) and t > now]
    latest_time = max(future_times) if future_times else now

    # ✅ Force round up to avoid overlap
    latest_time_plus_one = latest_time + timedelta(minutes=1)

    # ✅ Get next clean interval after the latest time
    start_time = get_next_interval_time(interval_minutes, after=latest_time_plus_one)

    for i, job in enumerate(job_queue):
        run_time = start_time + timedelta(minutes=i * interval_minutes)
        job["time"] = run_time
        job_id = f"{job['ticket']}_{run_time.strftime('%Y%m%d%H%M')}"
        job["job_id"] = job_id

        scheduler.add_job(
            send_message_to_ticket,
            "date",
            run_date=run_time,
            args=[
                email_entry.get().strip(),
                password_entry.get().strip(),
                job["ticket"],
                job["message"],
                job.get("last_comment", ""),
                job["check_last"],
                job["solve_ticket"],
                job["public_reply"],
            ],
            id=job_id,
            replace_existing=True,
        )

        scheduled_jobs.append(job)
        scheduled_times.append(run_time)
        scheduled_queue_times.append(run_time)  # ✅ Track for future scheduling

        scheduled_listbox.insert(
            tk.END,
            f"📤 {run_time.strftime('%H:%M')} → Ticket: {job['ticket']} | "
            f"Solve: {'Yes' if job['solve_ticket'] else 'No'} | "
            f"Public: {'Yes' if job['public_reply'] else 'No'} | "
            f"Check Last: {'Yes' if job['check_last'] else 'No'}"
        )

    job_queue.clear()
    queue_listbox.delete(0, tk.END)


def get_next_interval_time(interval_minutes, after=None):
    now = datetime.now().replace(second=0, microsecond=0)
    base_time = after if after and after > now else now

    remainder = base_time.minute % interval_minutes
    if remainder == 0 and base_time > now:
        return base_time
    else:
        minutes_to_add = interval_minutes - remainder if remainder else interval_minutes
        return base_time + timedelta(minutes=minutes_to_add)



def save_telegram_settings(token: str, chat_id: str):
    try:
        with open("telegram_config.json", "w") as f:
            json.dump({"token": token, "chat_id": chat_id}, f)
        print("[TELEGRAM] Settings saved.")
    except Exception as e:
        print(f"[ERROR] Could not save Telegram settings: {e}")


def load_telegram_settings():
    try:
        with open("telegram_config.json", "r") as f:
            config = json.load(f)
            telegram_token_entry.insert(0, config.get("token", ""))
            telegram_chatid_entry.insert(0, config.get("chat_id", ""))
        print("[TELEGRAM] Settings loaded.")
    except FileNotFoundError:
        print("[TELEGRAM] No saved settings found.")
    except Exception as e:
        print(f"[ERROR] Could not load Telegram settings: {e}")


# --- Telegram Functions ---
def send_telegram_message(bot_token: str, chat_id: str, text: str) -> bool:
    if not bot_token or not chat_id:
        print("[TELEGRAM] Bot token or chat ID missing.")
        return False
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    try:
        res = requests.post(url, data=payload, timeout=10)
        if res.status_code != 200:
            print(f"[TELEGRAM ERROR] Status {res.status_code}: {res.text}")
            return False
        else:
            print("[TELEGRAM] Message sent.")
            return True
    except Exception as e:
        print(f"[TELEGRAM EXCEPTION] {e}")
        return False


def fetch_chat_id_from_token(bot_token: str):
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            updates = response.json()
            print("Updates:", updates)  # Debug print
            messages = updates.get("result", [])
            if messages:
                return messages[-1]["message"]["chat"]["id"]
            else:
                print("[Chat ID] No messages found in updates.")
        else:
            print(f"[Chat ID Error] Status {response.status_code}: {response.text}")
    except Exception as e:
        print(f"[Chat ID Exception] {e}")
    return None


def test_telegram():
    bot_token = telegram_token_entry.get().strip()
    if not bot_token:
        mb.showerror("Missing Token", "Please enter your Telegram bot token first.")
        return
    chat_id = fetch_chat_id_from_token(bot_token)
    if not chat_id:
        mb.showerror(
            "No Chat Found",
            "Could not fetch your chat ID.\n\nMake sure:\n• You’ve started a conversation with your bot\n• Your token is correct",
        )
        return
    telegram_chatid_entry.delete(0, tk.END)
    telegram_chatid_entry.insert(0, str(chat_id))
    success = send_telegram_message(
        bot_token, str(chat_id), "✅ Test successful! Your bot is connected."
    )
    if success:
        save_telegram_settings(bot_token, str(chat_id))
        mb.showinfo(
            "Success", "✅ Telegram test message sent!\nChat ID has been auto-filled."
        )
    else:
        mb.showerror("Failed", "Bot token might be wrong or blocked by Telegram.")


# --- Scheduler setup ---
scheduler = BackgroundScheduler()
scheduled_jobs = []
job_queue = []
scheduled_times = []
manual_jobs = []
sent_log = []


# --- HTML Cleaning and Formatting ---
def clean_html(raw_html):
    soup = BeautifulSoup(raw_html, "html.parser")
    return soup.get_text(separator="\n").strip()


PERSISTENCE_FILE = "job_data.json"

PERSISTENCE_FILE = "job_data.json"

def save_jobs_to_file():
    try:
        def serialize_job(job):
            # Convert time to string only if it's a datetime object
            new_job = job.copy()
            if isinstance(new_job.get("time"), datetime):
                new_job["time"] = new_job["time"].strftime("%Y-%m-%d %H:%M:%S")
            return new_job

        data = {
            "job_queue": [
                {k: v for k, v in job.items() if k not in ("email", "password")}
                for job in job_queue
            ],
            "manual_jobs": [
                serialize_job({k: v for k, v in job.items() if k not in ("email", "password")})
                for job in manual_jobs
            ],
            "scheduled_jobs": [
                serialize_job({k: v for k, v in job.items() if k not in ("email", "password")})
                for job in scheduled_jobs
            ]
        }

        with open(PERSISTENCE_FILE, "w") as f:
            json.dump(data, f, indent=2)

        mb.showinfo("Success", "Jobs successfully saved to file.")
        print("[SAVE] Jobs saved.")

    except Exception as e:
        mb.showerror("Error", f"Failed to save jobs: {e}")

def load_jobs_from_file():
    if not os.path.exists(PERSISTENCE_FILE):
        mb.showwarning("Not Found", "No saved job file found.")
        return

    try:
        with open(PERSISTENCE_FILE, "r") as f:
            data = json.load(f)

        # Clear existing jobs and UI
        job_queue.clear()
        queue_listbox.delete(0, tk.END)
        manual_jobs.clear()
        manual_listbox.delete(0, tk.END)
        scheduled_jobs.clear()
        scheduled_listbox.delete(0, tk.END)
        scheduled_times.clear()
        scheduled_queue_times.clear()

        # Load job_queue
        for job in data.get("job_queue", []):
            job_queue.append(job)
            queue_listbox.insert(
                tk.END,
                f"📝 Ticket: {job['ticket']} | Solve: {'Yes' if job['solve_ticket'] else 'No'} | "
                f"Public: {'Yes' if job['public_reply'] else 'No'} | Check Last: {'Yes' if job['check_last'] else 'No'}"
            )

        # Load manual_jobs
        for job in data.get("manual_jobs", []):
            time_obj = datetime.strptime(job["time"], "%Y-%m-%d %H:%M:%S")
            job["time"] = time_obj
            job["job_id"] = f"{job['ticket']}_{time_obj.strftime('%Y%m%d%H%M')}"
            manual_jobs.append(job)

            if time_obj > datetime.now():
                scheduled_times.append(time_obj)

                scheduler.add_job(
                    send_message_to_ticket,
                    "date",
                    run_date=time_obj,
                    args=[
                        email_entry.get().strip(),
                        password_entry.get().strip(),
                        job["ticket"],
                        job["message"],
                        job.get("last_comment", ""),
                        job["check_last"],
                        job["solve_ticket"],
                        job["public_reply"]
                    ],
                    id=job["job_id"],
                    replace_existing=True
                )

            manual_listbox.insert(
                tk.END,
                f"Manual: {job['ticket']} at {time_obj.strftime('%H:%M')} | "
                f"Solve: {'Yes' if job['solve_ticket'] else 'No'} | "
                f"Public: {'Yes' if job['public_reply'] else 'No'} | "
                f"Check Last: {'Yes' if job['check_last'] else 'No'}"
            )

        # Load scheduled_jobs
        for job in data.get("scheduled_jobs", []):
            try:
                time_obj = datetime.strptime(job["time"], "%Y-%m-%d %H:%M:%S")
                job["time"] = time_obj
                job["job_id"] = f"{job['ticket']}_{time_obj.strftime('%Y%m%d%H%M')}"
                scheduled_jobs.append(job)

                if time_obj > datetime.now():
                    scheduled_times.append(time_obj)
                    scheduled_queue_times.append(time_obj)

                    scheduler.add_job(
                        send_message_to_ticket,
                        "date",
                        run_date=time_obj,
                        args=[
                            email_entry.get().strip(),
                            password_entry.get().strip(),
                            job["ticket"],
                            job["message"],
                            job.get("last_comment", ""),
                            job["check_last"],
                            job["solve_ticket"],
                            job["public_reply"]
                        ],
                        id=job["job_id"],
                        replace_existing=True
                    )

                scheduled_listbox.insert(
                    tk.END,
                    f"📤 {time_obj.strftime('%H:%M')} → Ticket: {job['ticket']} | "
                    f"Solve: {'Yes' if job['solve_ticket'] else 'No'} | "
                    f"Public: {'Yes' if job['public_reply'] else 'No'} | "
                    f"Check Last: {'Yes' if job['check_last'] else 'No'}"
                )
            except Exception as e:
                print(f"[ERROR] Failed to load scheduled job for ticket {job.get('ticket', '???')}: {e}")

        mb.showinfo("Loaded", "Jobs successfully loaded and scheduled.")
        print("[LOAD] Job data restored.")

    except Exception as e:
        mb.showerror("Error", f"Failed to load jobs: {e}")



def convert_formatting(text):
    text = re.sub(r"\[([^\]]+)]\s*\((https?://[^\)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"_(.*?)_", r"<i>\1</i>", text)
    return text


def format_message_with_html(text):
    lines = text.splitlines()
    html_lines = []
    in_list = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        formatted = convert_formatting(stripped)
        if stripped.startswith(("-", "•")):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{formatted[1:].strip()}</li>")
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<p>{formatted}</p>")
    if in_list:
        html_lines.append("</ul>")
    return "".join(html_lines)


# --- Zendesk API Calls ---
def get_last_comment(email, password, ticket_id):
    url = f"https://inventry.zendesk.com/api/v2/tickets/{ticket_id}/comments.json"
    try:
        response = requests.get(url, auth=(email, password))
        if response.status_code == 200:
            comments = response.json().get("comments", [])
            if comments:
                last_comment = comments[-1]
                return clean_html(
                    last_comment.get("html_body") or last_comment.get("body")
                )
    except Exception as e:
        print(f"[ERROR] Could not fetch last comment for ticket {ticket_id}: {e}")
    return ""


def send_message(email, password, ticket_id, message, solve_ticket, public_reply):
    url = f"https://inventry.zendesk.com/api/v2/tickets/{ticket_id}.json"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    }

    # ✨ Default values
    payload = {
        "ticket": {
            "comment": {
                "html_body": message,
                "public": public_reply,
            },
            "status": "solved" if solve_ticket else "open",
            "priority": "normal",
            "type": "incident",
            "custom_fields": [
                {"id": 360004384577, "value": "software"}  # Example field ID
            ],
        }
    }

    try:
        response = requests.put(url, headers=headers, data=json.dumps(payload), auth=(email, password))
        now_time = datetime.now().strftime("%H:%M:%S")

        if response.status_code == 200:
            log_text = f"✅ {now_time} → Ticket: {ticket_id} | Solved: {'Yes' if solve_ticket else 'No'}"
            print(f"[SUCCESS] {log_text}")
            sent_log.append(log_text)
            sent_listbox.insert(tk.END, log_text)

            # 🔔 Telegram update
            bot_token = telegram_token_entry.get().strip()
            chat_id = telegram_chatid_entry.get().strip()
            if bot_token and chat_id:
                status_text = "Solved ✅" if solve_ticket else "Open 🟡"
                reply_type = "Public Email 📤" if public_reply else "Internal Note 🛡️"
                telegram_msg = f"🎫 Ticket #{ticket_id} | {status_text} | {reply_type} | Sent at {now_time}"
                send_telegram_message(bot_token, chat_id, telegram_msg)
        else:
            print(f"[ERROR] Failed to update ticket #{ticket_id}: {response.status_code}")
            print(f"[DETAILS] {response.text}")

            if response.status_code == 422:
                print("[INFO] Retrying with plain text body...")
                payload["ticket"]["comment"].pop("html_body")
                payload["ticket"]["comment"]["body"] = message

                retry_response = requests.put(url, headers=headers, data=json.dumps(payload), auth=(email, password))
                if retry_response.status_code == 200:
                    log_text = f"✅ {now_time} → Ticket: {ticket_id} | Solved: {'Yes' if solve_ticket else 'No'} (plain text)"
                    print(f"[SUCCESS] {log_text}")
                    sent_log.append(log_text)
                    sent_listbox.insert(tk.END, log_text)
                else:
                    print(f"[RETRY ERROR] {retry_response.status_code}: {retry_response.text}")

    except Exception as e:
        print(f"[EXCEPTION] Error while sending to ticket #{ticket_id}: {str(e)}")


def send_message_to_ticket(
    email,
    password,
    ticket_id,
    message,
    original_last_comment,
    check_last,
    solve_ticket,
    public_reply,
):
    if check_last:
        current_last_comment = get_last_comment(email, password, ticket_id)
        if current_last_comment != original_last_comment:
            print(
                f"[SKIPPED] Ticket #{ticket_id} changed since scheduling. Not sending."
            )
            return
    send_message(email, password, ticket_id, message, solve_ticket, public_reply)


# --- Scheduling Helpers ---


# --- Preview popup ---
def preview_message_window(msg):
    win = tk.Toplevel()
    win.title("Preview Message")
    text = tk.Text(win, wrap="word", font=("Arial", 11))
    text.insert("1.0", msg)
    text.config(state="disabled")
    text.pack(expand=True, fill="both")
    scrollbar = tk.Scrollbar(win, command=text.yview)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    text.config(yscrollcommand=scrollbar.set)


# --- Last comment popup ---
def check_last_comment_popup(email, password, ticket):
    comment = get_last_comment(email, password, ticket)
    win = tk.Toplevel()
    win.title(f"Last Comment for Ticket {ticket}")
    text = tk.Text(win, wrap="word", font=("Arial", 11))
    text.insert("1.0", comment if comment else "[No comments found]")
    text.config(state="disabled")
    text.pack(expand=True, fill="both")
    scrollbar = tk.Scrollbar(win, command=text.yview)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    text.config(yscrollcommand=scrollbar.set)


# --- Delete selected jobs from listbox and data list ---
def delete_selected(event, listbox, data_list):
    sel = listbox.curselection()
    if sel:
        i = sel[0]
        listbox.delete(i)
        if i < len(data_list):
            del data_list[i]


# --- Countdown updater ---
def countdown_updater():
    while True:
        if scheduled_times:
            now = datetime.now()
            future = [t for t in scheduled_times if t > now]
            if future:
                next_job = min(future)
                time_left = int((next_job - now).total_seconds())
                mins, secs = divmod(time_left, 60)
                countdown_label.configure(text=f"⏳ Next: {mins:02}:{secs:02}")
            else:
                countdown_label.configure(text="✅ All jobs done")
                scheduled_times.clear()
        else:
            countdown_label.configure(text="⏳ No jobs scheduled")
        time.sleep(1)


# --- GUI Setup ---
set_appearance_mode("System")
set_default_color_theme("blue")
app = CTk()
app.geometry("760x900")
app.title("Zendesk Email Scheduler")

scrollable_frame = CTkScrollableFrame(app, width=740, height=880)
scrollable_frame.pack(padx=10, pady=10, fill="both", expand=True)
frame = scrollable_frame

CTkLabel(frame, text="Zendesk Email:").pack(pady=(5, 0))
email_entry = CTkEntry(frame, width=700)
email_entry.pack(pady=3)

CTkLabel(frame, text="Zendesk Password:").pack(pady=(5, 0))
password_entry = CTkEntry(frame, width=700, show="*")
password_entry.pack(pady=3)

CTkLabel(frame, text="Ticket ID:").pack(pady=(5, 0))
ticket_entry = CTkEntry(frame, width=700)
ticket_entry.pack(pady=3)

CTkLabel(frame, text="Message to Send:").pack(pady=(5, 0))
message_box = CTkTextbox(frame, width=700, height=130)
message_box.pack(pady=3)

# 🔁 Enable undo/redo
message_box.configure(undo=True, maxundo=50)
message_box.bind("<Control-z>", lambda e: message_box.edit_undo())
message_box.bind("<Control-y>", lambda e: message_box.edit_redo())



def add_bullet(event=None):
    index = message_box.index("insert linestart")
    current_line = message_box.get(index, f"{index} lineend")

    if current_line.strip().startswith("•"):
        # Remove bullet
        new_line = current_line.replace("•", "", 1).lstrip()
        message_box.delete(index, f"{index} lineend")
        message_box.insert(index, new_line)
    else:
        # Add bullet
        message_box.delete(index, f"{index} lineend")
        message_box.insert(index, f"• {current_line.strip()}")

    return "break"



message_box.bind("<Control-Shift-BackSpace>", add_bullet)

# 💬 The rest of the UI — Queue system, manual scheduler, interval menu, buttons, listboxes, countdown — continue below

# NOTE: The full script exceeds response length. Reply with **“next”** and I’ll paste the second half.
# Per-job check last email toggle
check_last_var = tk.BooleanVar(value=True)
check_last_checkbox = CTkCheckBox(
    frame,
    text="Check Last Comment Before Sending (for this job)",
    variable=check_last_var,
)
check_last_checkbox.pack(pady=5)

# Per-job solve ticket toggle
solve_ticket_var = tk.BooleanVar(value=False)
solve_ticket_switch = CTkSwitch(
    frame,
    text="Mark Ticket as Solved (for this job)",
    variable=solve_ticket_var,
    onvalue=True,
    offvalue=False,
)
solve_ticket_switch.pack(pady=5)

# Per-job public/internal toggle
public_reply_var = tk.BooleanVar(value=True)
public_reply_switch = CTkSwitch(
    frame,
    text="Public Reply (disable for Internal Note)",
    variable=public_reply_var,
    onvalue=True,
    offvalue=False,
)
public_reply_switch.pack(pady=5)

# Buttons frame 1
button_frame = CTkFrame(frame)
button_frame.pack(pady=5)


def add_to_queue():
    email = email_entry.get().strip()
    password = password_entry.get().strip()
    ticket = ticket_entry.get().strip()
    message = message_box.get("1.0", tk.END).strip()
    check_last = check_last_var.get()
    solve_ticket = solve_ticket_var.get()  # ✅ Get solve ticket status
    public_reply = public_reply_var.get()  # ✅ Get public/internal note status

    if not (email and password and ticket and message):
        mb.showwarning("Missing Info", "Please fill all fields before adding to queue.")
        return

    html_message = format_message_with_html(message)
    last_comment = get_last_comment(email, password, ticket) if check_last else ""

    job_queue.append(
        {
            "email": email,
            "password": password,
            "ticket": ticket,
            "message": html_message,
            "last_comment": last_comment,
            "check_last": check_last,
            "solve_ticket": solve_ticket,
            "public_reply": public_reply,
        }
    )

    queue_listbox.insert(
        tk.END,
        f"📝 Ticket: {ticket} | Solve: {'Yes' if solve_ticket else 'No'} | Public: {'Yes' if public_reply else 'No'} | Check Last: {'Yes' if check_last else 'No'}",
    )

    ticket_entry.delete(0, tk.END)
    message_box.delete("1.0", tk.END)


def preview_message():
    msg = message_box.get("1.0", tk.END).strip()
    if not msg:
        mb.showerror("Empty Message", "There is no message to preview.")
        return
    preview_message_window(msg)


def check_last_email():
    email = email_entry.get().strip()
    password = password_entry.get().strip()
    ticket = ticket_entry.get().strip()
    if not (email and password and ticket):
        mb.showerror(
            "Missing Info",
            "Please fill Zendesk Email, Password and Ticket ID to check last email.",
        )
        return
    check_last_comment_popup(email, password, ticket)


def clear_queue():
    job_queue.clear()
    queue_listbox.delete(0, tk.END)


def edit_job_popup(index, job_list, listbox, is_manual=False):
    job = job_list[index]

    popup = CTkToplevel()
    popup.title("✏️ Edit Job")
    popup.attributes("-topmost", True)

    popup.update_idletasks()
    w, h = 460, 500
    x = (popup.winfo_screenwidth() // 2) - (w // 2)
    y = (popup.winfo_screenheight() // 2) - (h // 2)
    popup.geometry(f"{w}x{h}+{x}+{y}")

    CTkLabel(popup, text="🎫 Ticket ID:").pack(pady=(10, 0))
    ticket_entry = CTkEntry(popup, width=400)
    ticket_entry.insert(0, job.get("ticket", ""))
    ticket_entry.pack(pady=5)

    CTkLabel(popup, text="📝 Message:").pack(pady=(10, 0))
    message_box = CTkTextbox(popup, width=400, height=130)
    message_box.insert("1.0", clean_html(job.get("message", "")))
    message_box.pack(pady=5)

    from tkinter import ttk
    ttk.Separator(popup).pack(fill="x", pady=10)

    solve_var = tk.BooleanVar(value=job.get("solve_ticket", False))
    CTkSwitch(popup, text="✅ Mark as Solved", variable=solve_var).pack(pady=5)

    public_var = tk.BooleanVar(value=job.get("public_reply", False))
    CTkSwitch(popup, text="📤 Public Reply", variable=public_var).pack(pady=5)

    check_last_var_popup = tk.BooleanVar(value=job.get("check_last", False))
    CTkCheckBox(popup, text="🔁 Check Last Comment", variable=check_last_var_popup).pack(pady=5)

    popup.after(100, lambda: ticket_entry.focus_set())

    if "time" in job:
        CTkLabel(popup, text="⏰ Edit Scheduled Time:").pack(pady=(10, 0))
        time_frame = CTkFrame(popup)
        time_frame.pack(pady=5)

        time_obj = job["time"]
        if isinstance(time_obj, str):
            time_obj = datetime.strptime(time_obj, "%Y-%m-%d %H:%M:%S")

        hour_var = tk.StringVar(value=f"{time_obj.hour:02d}")
        minute_var = tk.StringVar(value=f"{time_obj.minute:02d}")

        hour_frame = CTkFrame(time_frame)
        hour_frame.pack(side=tk.LEFT, padx=10)
        CTkLabel(hour_frame, text="Hour").pack()
        CTkEntry(hour_frame, textvariable=hour_var, width=60, justify="center").pack()

        minute_frame = CTkFrame(time_frame)
        minute_frame.pack(side=tk.LEFT, padx=10)
        CTkLabel(minute_frame, text="Minute").pack()
        CTkEntry(minute_frame, textvariable=minute_var, width=60, justify="center").pack()

    ttk.Separator(popup).pack(fill="x", pady=10)
        
    def save_changes():
        job["ticket"] = ticket_entry.get().strip()
        raw_message = message_box.get("1.0", tk.END).strip()
        job["message"] = format_message_with_html(raw_message)
        job["solve_ticket"] = solve_var.get()
        job["public_reply"] = public_var.get()
        job["check_last"] = check_last_var_popup.get()

        try:
            if "time" in job:
                new_hour = int(hour_var.get())
                new_minute = int(minute_var.get())

                if not (0 <= new_hour < 24 and 0 <= new_minute < 60):
                    raise ValueError

                new_time = datetime.now().replace(hour=new_hour, minute=new_minute, second=0, microsecond=0)
                if new_time < datetime.now():
                    new_time += timedelta(days=1)

                old_time = job.get("time")
                old_job_id = job.get("job_id")

                job["time"] = new_time
                job_id = f"{job['ticket']}_{new_time.strftime('%Y%m%d%H%M')}"
                job["job_id"] = job_id

                # Remove old scheduled job from APScheduler
                if old_job_id:
                    try:
                        scheduler.remove_job(old_job_id)
                    except Exception as e:
                        print(f"[WARN] Could not remove old job: {old_job_id} → {e}")

                # Update scheduled time tracking list
                if isinstance(old_time, datetime) and old_time in scheduled_queue_times:
                    scheduled_queue_times.remove(old_time)
                scheduled_queue_times.append(new_time)

                if isinstance(old_time, datetime) and old_time in scheduled_times:
                    scheduled_times.remove(old_time)
                scheduled_times.append(new_time)


                # Add updated job to scheduler
                scheduler.add_job(
                    send_message_to_ticket,
                    "date",
                    run_date=new_time,
                    args=[
                        email_entry.get().strip(),
                        password_entry.get().strip(),
                        job["ticket"],
                        job["message"],
                        job.get("last_comment", ""),
                        job["check_last"],
                        job["solve_ticket"],
                        job["public_reply"],
                    ],
                    id=job_id,
                    replace_existing=True
                )

                # Update job in the correct job list
                if is_manual:
                    for i, j in enumerate(manual_jobs):
                        if j == job:
                            manual_jobs[i] = job
                            break
                else:
                    for i, j in enumerate(scheduled_jobs):
                        if j == job:
                            scheduled_jobs[i] = job
                            break

        except ValueError:
            mb.showerror("Invalid Time", "Please enter valid hour (0–23) and minute (0–59).")
            return

        # Update listbox label
        if "time" in job:
            display = f"{'Manual:' if is_manual else '📤'} {job['ticket']} at {job['time'].strftime('%H:%M')} | Solve: {'Yes' if job['solve_ticket'] else 'No'} | Public: {'Yes' if job['public_reply'] else 'No'} | Check Last: {'Yes' if job['check_last'] else 'No'}"
        else:
            display = f"📝 Ticket: {job['ticket']} | Solve: {'Yes' if job['solve_ticket'] else 'No'} | Public: {'Yes' if job['public_reply'] else 'No'} | Check Last: {'Yes' if job['check_last'] else 'No'}"

        listbox.delete(index)
        listbox.insert(index, display)
        popup.destroy()

    popup.bind("<Return>", lambda e: save_changes())
    popup.bind("<Escape>", lambda e: popup.destroy())

    btn_frame = CTkFrame(popup)
    btn_frame.pack(pady=15)
    CTkButton(btn_frame, text="💾 Save", command=save_changes).pack(side=tk.LEFT, padx=10)
    CTkButton(btn_frame, text="❌ Cancel", command=popup.destroy, fg_color="gray").pack(side=tk.LEFT, padx=10)

    





CTkButton(button_frame, text="➕ Add to Queue", command=add_to_queue).pack(
    side=tk.LEFT, padx=5
)
CTkButton(button_frame, text="👁 Preview Message", command=preview_message).pack(
    side=tk.LEFT, padx=5
)
CTkButton(button_frame, text="📩 Check Last Email", command=check_last_email).pack(
    side=tk.LEFT, padx=5
)

# Interval selection
CTkLabel(frame, text="⏱ Select Time Between Emails:").pack(pady=(10, 0))
interval_option = CTkOptionMenu(
    frame, values=["15 min between emails", "30 min between emails"]
)
interval_option.set("15 min between emails")
interval_option.pack(pady=5)

# Schedule and clear buttons frame 2
buttons_frame_2 = CTkFrame(frame)
buttons_frame_2.pack(pady=5)
CTkButton(buttons_frame_2, text="✅ Schedule All", command=schedule_all_jobs).pack(
    side=tk.LEFT, padx=15
)
CTkButton(buttons_frame_2, text="🗑 Clear Queue", command=clear_queue).pack(
    side=tk.LEFT, padx=15
)
# Save/Load Job Buttons
file_button_frame = CTkFrame(frame)
file_button_frame.pack(pady=(10, 5))

CTkButton(file_button_frame, text="💾 Save Jobs to File", command=save_jobs_to_file).pack(side=tk.LEFT, padx=10)
CTkButton(file_button_frame, text="📂 Load Jobs from File", command=load_jobs_from_file).pack(side=tk.LEFT, padx=10)

# Queued Jobs Listbox
CTkLabel(frame, text="📋 Queued Jobs:").pack(pady=(10, 0))
queue_frame = tk.Frame(frame)
queue_frame.pack()
queue_scrollbar = tk.Scrollbar(queue_frame)
queue_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
queue_listbox = tk.Listbox(
    queue_frame, width=90, height=6, yscrollcommand=queue_scrollbar.set
)
queue_listbox.pack(side=tk.LEFT, fill=tk.BOTH)
queue_scrollbar.config(command=queue_listbox.yview)
queue_listbox.bind("<Delete>", lambda e: delete_selected(e, queue_listbox, job_queue))
queue_listbox.bind("<Delete>", lambda e: delete_selected(e, queue_listbox, job_queue))


# Scheduled Jobs Listbox
CTkLabel(frame, text="📆 Scheduled Jobs:").pack(pady=(10, 0))
scheduled_frame = tk.Frame(frame)
scheduled_frame.pack()
scheduled_scrollbar = tk.Scrollbar(scheduled_frame)
scheduled_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
scheduled_listbox = tk.Listbox(
    scheduled_frame, width=90, height=10, yscrollcommand=scheduled_scrollbar.set
)
scheduled_listbox.pack(side=tk.LEFT, fill=tk.BOTH)
scheduled_scrollbar.config(command=scheduled_listbox.yview)
scheduled_listbox.bind(
    "<Delete>", lambda e: delete_selected(e, scheduled_listbox, scheduled_times)
)

# Manual Job Scheduler
manual_frame = CTkFrame(frame)
manual_frame.pack(pady=(20, 5), fill="x")
CTkLabel(manual_frame, text="Manual Job Scheduler (Set Time and Schedule):").pack()

time_frame = CTkFrame(manual_frame)
time_frame.pack(pady=5)
hour_var = tk.StringVar(value="12")
minute_var = tk.StringVar(value="00")
CTkLabel(time_frame, text="Hour:").pack(side=tk.LEFT, padx=(0, 5))
hour_menu = CTkOptionMenu(
    time_frame, values=[f"{i:02}" for i in range(24)], variable=hour_var, width=80
)
hour_menu.pack(side=tk.LEFT, padx=(0, 15))
CTkLabel(time_frame, text="Minute:").pack(side=tk.LEFT, padx=(0, 5))
minute_menu = CTkOptionMenu(
    time_frame, values=[f"{i:02}" for i in range(60)], variable=minute_var, width=80
)
minute_menu.pack(side=tk.LEFT, padx=(0, 15))

def add_manual_job():
    email = email_entry.get().strip()
    password = password_entry.get().strip()
    ticket = ticket_entry.get().strip()
    message = message_box.get("1.0", tk.END).strip()
    check_last = check_last_var.get()
    solve_ticket = solve_ticket_var.get()
    public_reply = public_reply_var.get()

    if not (email and password and ticket and message):
        mb.showwarning("Missing Info", "Please fill all fields before adding manual job.")
        return

    html_message = format_message_with_html(message)

    hour = int(hour_var.get())
    minute = int(minute_var.get())
    now = datetime.now()
    run_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if run_time <= now:
        run_time += timedelta(days=1)

    last_comment = get_last_comment(email, password, ticket) if check_last else ""
    job_id = f"{ticket}_{run_time.strftime('%Y%m%d%H%M')}"

    job = {
        "email": email,
        "password": password,
        "ticket": ticket,
        "message": html_message,
        "last_comment": last_comment,
        "check_last": check_last,
        "solve_ticket": solve_ticket,
        "public_reply": public_reply,
        "time": run_time,
        "job_id": job_id,
    }

    manual_jobs.append(job)
    scheduled_times.append(run_time)

    scheduler.add_job(
        lambda job=job: send_message_to_ticket(
            email_entry.get().strip(),
            password_entry.get().strip(),
            job["ticket"],
            job["message"],
            job.get("last_comment", ""),
            job["check_last"],
            job["solve_ticket"],
            job["public_reply"],
        ),
        "date",
        run_date=run_time,
        id=job_id,
        replace_existing=True,
    )

    manual_listbox.insert(
        tk.END,
        f"Manual: {ticket} at {run_time.strftime('%H:%M')} | "
        f"Solve: {'Yes' if solve_ticket else 'No'} | "
        f"Public: {'Yes' if public_reply else 'No'} | "
        f"Check Last: {'Yes' if check_last else 'No'}"
    )

    ticket_entry.delete(0, tk.END)
    message_box.delete("1.0", tk.END)


def reschedule_manual_job(job, index, listbox):
    try:
        new_time = job["time"]
        if isinstance(new_time, str):
            new_time = datetime.strptime(new_time, "%Y-%m-%d %H:%M:%S")

        job_id = f"{job['ticket']}_{new_time.strftime('%Y%m%d%H%M')}"
        job["job_id"] = job_id

        # Remove previous job with same ID if exists
        for j in scheduler.get_jobs():
            if j.id == job_id:
                scheduler.remove_job(j.id)

        # Clean up old times
        for t in scheduled_times[:]:
            if abs((t - new_time).total_seconds()) < 60:
                scheduled_times.remove(t)
        scheduled_times.append(new_time)

        scheduler.add_job(
            lambda job=job: send_message_to_ticket(
                email_entry.get().strip(),
                password_entry.get().strip(),
                job["ticket"],
                job["message"],
                job.get("last_comment", ""),
                job["check_last"],
                job["solve_ticket"],
                job["public_reply"],
            ),
            "date",
            run_date=new_time,
            id=job_id,
            replace_existing=True,
        )

        # Update listbox
        listbox.delete(index)
        listbox.insert(
            index,
            f"Manual: {job['ticket']} at {new_time.strftime('%H:%M')} | "
            f"Solve: {'Yes' if job['solve_ticket'] else 'No'} | "
            f"Public: {'Yes' if job['public_reply'] else 'No'} | "
            f"Check Last: {'Yes' if job['check_last'] else 'No'}"
        )

    except Exception as e:
        mb.showerror("Reschedule Failed", f"Could not reschedule job.\n{e}")



CTkButton(manual_frame, text="➕ Add Manual Job", command=add_manual_job).pack(pady=5)

# Manual jobs listbox
manual_list_frame = tk.Frame(frame)
manual_list_frame.pack(pady=5)
manual_scrollbar = tk.Scrollbar(manual_list_frame)
manual_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
manual_listbox = tk.Listbox(
    manual_list_frame, width=90, height=6, yscrollcommand=manual_scrollbar.set
)
manual_listbox.pack(side=tk.LEFT, fill=tk.BOTH)
manual_scrollbar.config(command=manual_listbox.yview)
manual_listbox.bind(
    "<Delete>", lambda e: delete_selected(e, manual_listbox, manual_jobs)
)

# Enable double-click editing for each job type
queue_listbox.bind("<Double-Button-1>", lambda e: edit_job_popup(queue_listbox.curselection()[0], job_queue, queue_listbox))

manual_listbox.bind("<Double-Button-1>", lambda e: edit_job_popup(manual_listbox.curselection()[0], manual_jobs, manual_listbox, is_manual=True))

scheduled_listbox.bind("<Double-Button-1>", lambda e: edit_job_popup(scheduled_listbox.curselection()[0], scheduled_jobs, scheduled_listbox, is_manual=False))

# Sent Log
CTkLabel(frame, text="📨 Sent Log:").pack(pady=(10, 0))
sent_frame = tk.Frame(frame)
sent_frame.pack()
sent_scrollbar = tk.Scrollbar(sent_frame)
sent_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
sent_listbox = tk.Listbox(
    sent_frame, width=90, height=8, yscrollcommand=sent_scrollbar.set
)
sent_listbox.pack(side=tk.LEFT, fill=tk.BOTH)
sent_scrollbar.config(command=sent_listbox.yview)

# Countdown Timer
countdown_label = CTkLabel(frame, text="⏳ No jobs scheduled", font=("Arial", 14))
countdown_label.pack(pady=15)

# Start countdown + scheduler
threading.Thread(target=countdown_updater, daemon=True).start()
scheduler.start()

# 🤖 Telegram Setup Fields
CTkLabel(frame, text="🤖 Telegram Bot Token:").pack(pady=(10, 0))
telegram_token_entry = CTkEntry(frame, width=700)
telegram_token_entry.pack(pady=3)

CTkLabel(frame, text="📨 Telegram Chat ID:").pack(pady=(5, 0))
telegram_chatid_entry = CTkEntry(frame, width=700)
telegram_chatid_entry.pack(pady=3)

CTkButton(frame, text="🧪 Test Telegram", command=test_telegram).pack(pady=5)
CTkEntry(frame, width=700)
telegram_chatid_entry.pack(pady=3)

load_telegram_settings()

app.mainloop()
