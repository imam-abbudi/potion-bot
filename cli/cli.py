import requests
import hashlib
import sys
import os
import threading
import socketio
from keyauth import Keyauth
from datetime import datetime
import json
import fade
import re
import time
from termcolor import colored
from solders.keypair import Keypair
from solana.rpc.api import Client
import base58
import re
from swaps import raydium, solutils

os.system('cls')
BASE_URL = 'http://162.33.177.57:8000'
sio = socketio.Client()
DATA_FILE = 'config.json'
CONFIG_PATH = 'config.json'
config = {
    'API_KEY': 'e502cd93180ba88db3f55242a66a6db8f690',
    'USER_IDS': ['elonmusk', 'another_user_id'],
    'private_key': 'your_private_key',
    'sol_amount': 0.01,  # Default SOL amount to buy
    'rpc': 'https://api.mainnet-beta.solana.com/',
    'rpc_headers': {},
    'profiles': {}  # Dictionary to store task profiles
}

if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH, 'r') as config_file:
        config.update(json.load(config_file))

max_user_limit = 20
COMPUTE_UNITS = config.get('fee', 0.00025)
SLIPPAGE = config.get('slippage', 0.05)

def load_config():
    if not os.path.exists(DATA_FILE) or os.stat(DATA_FILE).st_size == 0:
        return {}

    with open(DATA_FILE, 'r') as f:
        return json.load(f)
        
def calculate_file_checksum(file_path):
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def keyauth_login(client):
    username = input("Enter your username: ")
    password = input("Enter your password: ")
    print()

    # Start the loading animation in a separate thread
    stop_event = threading.Event()
    loading_thread = threading.Thread(target=loading_animation, args=(stop_event,))
    loading_thread.start()

    try:
        if client.login(username, password):
            stop_event.set()
            loading_thread.join()
            print("\rLogin successful!                     ")
            return username
        else:
            stop_event.set()
            loading_thread.join()
            print("\rLogin failed. Exiting...              ")
            exit()
    except Exception as e:
        stop_event.set()
        loading_thread.join()
        print(f"\rAn error occurred: {e}                ")
        exit()

def keyauth_register(client):
    username = input("Enter your desired username: ")
    password = input("Enter your desired password: ")
    license_key = input("Please enter your license key: ")
    if client.register(username, password, license_key):
        print("Registration successful!")
        return username
    else:
        print("Registration failed. Exiting...")
        exit()

def authenticate_with_keyauth():
    application_name = "Potion Bot"
    owner_id = "FuBzA4YHej"
    application_secret = "9c2d2cd36bb20178ee164d46e4ac08e3571547148db42f020e2c2622326b6476"
    version = "1.0"

    file_hash = calculate_file_checksum(sys.argv[0])

    client = Keyauth(
        name=application_name,
        owner_id=owner_id,
        secret=application_secret,
        version=version,
        file_hash=file_hash
    )
    print("1. Login")
    print("2. Register")
    print("3. Quit Program")
    choice = input("\nChoose an option: ").strip()
    print()

    if choice == '1':
        username = keyauth_login(client)
        os.system(f'title Potion Bot v1.0.3 - Signed in as {username}')
        return username
    elif choice == '2':
        username = keyauth_register(client)
        return username
    elif choice == '3':
        quit()
    else:
        print("Invalid choice. Exiting...")
        exit()

def watch_account(user_id, account_names):
    accounts = account_names.split(",")
    for account_name in accounts:
        account_name = account_name.strip()
        response = requests.post(f"{BASE_URL}/watch", json={'user_id': user_id, 'account_name': account_name})
        if response.status_code == 200:
            print(f"\nStarted watching {account_name}. Please hit 'q' and enter to stop monitoring events.")
        else:
            try:
                error_message = response.json().get('message', 'Unknown error')
            except json.JSONDecodeError:
                error_message = response.text
            print(f"Failed to watch account: {response.status_code} - {error_message}")

def fetch_watched_accounts():
    response = requests.get(f"{BASE_URL}/get_watched_accounts")
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Failed to fetch watched accounts: {response.status_code} - {response.text}")
        return {}

def stop_watch_account_backend(user_id, account_name):
    response = requests.post(f"{BASE_URL}/stop_watch", json={'user_id': user_id, 'account_name': account_name})
    if response.status_code == 200:
        print(f"Successfully stopped watching {account_name}")
    else:
        try:
            error_message = response.json().get('message', 'Unknown error')
        except json.JSONDecodeError:
            error_message = response.text
        print(f"Failed to stop watching account: {response.status_code} - {error_message}")

@sio.event
def connect():
    print("Connected to the backend")

@sio.event
def disconnect():
    print("Disconnected from the backend")

def send_discord_notification(task, tweet, tweet_text):
    webhook_url = task.get('discord_webhook')
    if not webhook_url:
        return
    
    contract_addresses = detect_contract_address(tweet_text)
    contract_address = contract_addresses[0] if contract_addresses else "No contract found"
    
    embed = {
        "title": "New Tweet Found • View Post",
        "description": f"**Tweet Text** ```{tweet_text}```",
        "url": f"https://twitter.com/{tweet['author']['handle']}/status/{tweet['id']}",
        "color": 41,
        "thumbnail": {
            "url": tweet['author']['profile']['avatar']
        },
        "fields": [
            {"name": "From", "value": f"```@{tweet['author']['handle']}```", "inline": True},
            {"name": "Task Name", "value": f"```{task['name']}```", "inline": True},
            {"name": "Contract address", "value": f"```{contract_address}```", "inline": True}
        ]
    }
    
    payload = {
        "username": "Potion Bot",
        "avatar_url": "https://media.discordapp.net/attachments/1248415809047625810/1249960041369567262/7BC36FA8-8907-4014-8A0D-D31BA7219028.jpg?ex=66693380&is=6667e200&hm=4d3549a8ad46101ec518328e1f5c633735fe9616c36726a760cae387b446a8d9&=",
        "embeds": [embed],
        "attachments": []
    }
    
    response = requests.post(webhook_url, json=payload)
    if response.status_code != 204:
        print(f"Failed to send Discord notification: {response.status_code} - {response.text}")

with open(DATA_FILE, 'r') as f:
    data = json.load(f)


def buy_token(coin_address, sol_amount, keypair):
    # Load RPC URL from buy settings
    with open(DATA_FILE, 'r') as f:
        data = json.load(f)
    rpc_url = data.get('buy_settings', {}).get('RPC', 'https://api.mainnet-beta.solana.com')

    client = Client(rpc_url)
    swapper = raydium.RaySwap(client, coin_address, sol_amount, keypair)

    start_time = time.time()  # Record the start time
    result = swapper.buy()
    end_time = time.time()  # Record the end time

    elapsed_time = end_time - start_time  # Calculate elapsed time

    if result:
        current_time = datetime.now()
        print(f"\033[0;32mINFO: [{current_time}] - Order Filled: {result} with {sol_amount} SOL in {elapsed_time:.2f} seconds.\033[0m")
    else:
        print(f"Failed to buy token: {coin_address}")

# Load keypair from data.json
with open(DATA_FILE, 'r') as f:
    data = json.load(f)
wallet_data = data.get("wallet")
if wallet_data:
    keypair = Keypair.from_bytes(base58.b58decode(wallet_data['privateKey']))

keypair = None
if wallet_data:
    keypair = Keypair.from_bytes(base58.b58decode(wallet_data['privateKey']))

def buy_pump_fun(contract_address: str, sol_amount: float, api_key: str):
    start_time = time.time()
    current_time = datetime.now()
    print(f"\033[0;35mINFO: [{current_time}] - Attempting to swap {contract_address} via Pump.Fun...\033[0m")
    url = f"https://pumpportal.fun/api/trade?api-key={api_key}"
    payload = {
        "action": "buy",
        "mint": contract_address,
        "amount": sol_amount,
        "denominatedInSol": "true",
        "slippage": config['buy_settings'].get('Pump.fun Slippage', 1000),  # percent slippage allowed
        "priorityFee": config['buy_settings'].get('Pump.fun Prio Fee', 0.01),  # amount to use as Jito tip or priority fee
        "pool": "pump"  # exchange to trade on. "pump" or "raydium"
    }
    response = requests.post(url, data=payload)

    if response.status_code == 200:
        current_time = datetime.now()
        data = response.json()
        transaction_id = data.get("signature")
        end_time = time.time()
        elapsed_time = end_time - start_time
        print(f"\033[0;32mINFO: [{current_time}] - Order Filled: {transaction_id} with {sol_amount} SOL in {elapsed_time:.2f} seconds.\033[0m")
    else:
        print(f"INFO: [{current_time}] Error: {response.status_code} - {response.text}")

@sio.on('event')
def on_event(data):
    global stop_monitoring
    tweet = data['event']['tweet']
    tweet_text = tweet['body']['text']
    created_at = datetime.fromtimestamp(tweet['created_at'] / 1000.0)
    task = current_task  # Ensure current_task is set globally or passed in
    output_text = f"Received tweet at {created_at} - Text: {tweet_text}\n"

    print(output_text)
    urls = tweet['body'].get('urls', [])
    for url_info in urls:
        url = url_info['url']
        if 'pump.fun' in url:
            print(f"Detected pump.fun URL: {url}")
            # Extract the contract address from the URL
            match = re.search(r'pump\.fun/([A-HJ-NP-Za-km-z1-9]+)', url)
            if match:
                contract_address = match.group(1)
                print(f"Extracted contract address: {contract_address}")
                # If AFK mode is on, automatically buy from pump.fun
                if task.get('afk_mode'):
                    buy_pump_fun(contract_address, task['snipe_amount'], config['wallet']['apiKey'])
        else:
            print(f"URL is not from pump.fun: {url}")

    # Handle AFK Mode
    if task.get('afk_mode'):
        addresses = detect_contract_address(tweet_text)
        if addresses:
            for address in addresses:
                buy_token(address, task['snipe_amount'], keypair)  # Ensure `keypair` is defined globally or passed in

    # Handle Notifications
    if task.get('notifications'):
        send_discord_notification(task, tweet, tweet_text)

def create_task():
    print("\nSelect a task type:")
    task_types = ["Standard User Monitor"]
    for idx, task_type in enumerate(task_types):
        print(f"{idx + 1}. {task_type}")
    selected_task_type = task_types[int(input("\nChoose a task type: ").strip()) - 1]
    twitter_handles = input("Enter Twitter handles to monitor (comma-separated): ")
    task_name = input("Enter a name for this task: ")
    afk_mode = input("AFK Mode (y/n)? ").lower() == 'y'
    notifications = input("Notifications (y/n)? ").lower() == 'y'
    discord_webhook = input("Enter Discord Webhook URL (if notifications are enabled): ").strip() if notifications else None
    snipe_amount = float(input("Enter Snipe Amount (SOL): ").strip())

    task = {
        "name": task_name,
        "handles": twitter_handles.split(","),
        "type": selected_task_type,
        "afk_mode": afk_mode,
        "notifications": notifications,
        "discord_webhook": discord_webhook,
        "snipe_amount": snipe_amount
    }

    if not os.path.exists(DATA_FILE) or os.stat(DATA_FILE).st_size == 0:
        with open(DATA_FILE, 'w') as f:
            json.dump({"tasks": []}, f)
    with open(DATA_FILE, 'r') as f:
        data = json.load(f)
    data["tasks"].append(task)
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f)
    print(f"Task '{task_name}' created successfully! Press any key to return to the menu.")
    input()

def delete_task():
    if not os.path.exists(DATA_FILE) or os.stat(DATA_FILE).st_size == 0:
        print("No tasks found. Press any key to return to the menu.")
        input()
        return

    with open(DATA_FILE, 'r') as f:
        data = json.load(f)

    if not data["tasks"]:
        print("No tasks found. Press any key to return to the menu.")
        input()
        return

    # Get the current theme
    theme = data.get("theme", "purpleblue")
    color_map = {
        "purpleblue": "blue",
        "greenblue": "green",
        "water": "cyan",
        "fire": "red",
        "pinkred": "magenta",
        "purplepink": "magenta",
        "brazil": "yellow"
    }
    task_color = color_map.get(theme, "blue")

    print("Select a task to delete:")
    tasks = data["tasks"]
    for idx, task in enumerate(tasks):
        task_type = task.get('type', 'Standard User Monitor')
        task_name = f"{task['name']} (Task Type: {task_type})"
        print(colored(f"{idx + 1}. {task_name}", task_color, attrs=['underline']))

    selected_task_idx = int(input("Choose a task: ").strip()) - 1
    deleted_task = tasks.pop(selected_task_idx)

    with open(DATA_FILE, 'w') as f:
        json.dump(data, f)

    print(f"Task '{deleted_task['name']}' deleted successfully! Press any key to return to the menu.")
    input()

global stop_monitoring, current_task
stop_monitoring = False

def start_task(username):
    global stop_monitoring, current_task
    stop_monitoring = False
    if not os.path.exists(DATA_FILE) or os.stat(DATA_FILE).st_size == 0:
        print("No tasks found. Create a task first. Press any key to return to the menu.")
        input()
        return
    with open(DATA_FILE, 'r') as f:
        data = json.load(f)
    if not data["tasks"]:
        print("No tasks found. Create a task first. Press any key to return to the menu.")
        input()
        return

    # Get the current theme
    theme = data.get("theme", "purpleblue")
    color_map = {
        "purpleblue": "blue",
        "greenblue": "green",
        "water": "cyan",
        "fire": "red",
        "pinkred": "magenta",
        "purplepink": "magenta",
        "brazil": "yellow"
    }
    task_color = color_map.get(theme, "blue")

    print()
    print("Select a task to start:")
    tasks = data["tasks"]
    for idx, task in enumerate(tasks):
        task_type = task.get('type', 'Standard User Monitor')
        task_name = f"{task['name']} (Task Type: {task_type})"
        print(colored(f"{idx + 1}. {task_name}", task_color, attrs=['underline']))

    selected_task = tasks[int(input("\nChoose a task: ").strip()) - 1]
    current_task = selected_task
    account_names = ",".join(selected_task["handles"])
    watch_account(username, account_names)
    while True:
        if input() == 'q':
            stop_monitoring = True
            watched_accounts = fetch_watched_accounts()
            for handle in selected_task["handles"]:
                for user_id, account_handle in watched_accounts.items():
                    if account_handle == handle:
                        stop_watch_account_backend(user_id, handle)
            sio.disconnect()
            break

def generate_wallet():
    response = requests.post("https://pumpportal.fun/api/create-wallet")
    if response.status_code == 200:
        wallet_data = response.json()
        if not os.path.exists(DATA_FILE) or os.stat(DATA_FILE).st_size == 0:
            with open(DATA_FILE, 'w') as f:
                json.dump({"tasks": [], "wallet": wallet_data}, f)
        else:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
            data["wallet"] = wallet_data
            with open(DATA_FILE, 'w') as f:
                json.dump(data, f)
        print("Wallet generated successfully!")
        print(f"Public Key: {wallet_data['walletPublicKey']}")
    else:
        print(f"Failed to generate wallet: {response.status_code} - {response.text}")
    input("Press any key to return to the menu.")

def configurations_menu():
    while True:
        os.system('cls')
        display_configurations_banner()
        choice = input("Enter choice: ")
        if choice == '1':
            generate_wallet()
        elif choice == '2':
            export_private_key()
        elif choice == '3':
            change_theme()
        elif choice == '4':
            buy_settings_menu()
        elif choice == 'B'.lower():
            break
        else:
            print("Invalid choice. Please try again.")

def buy_settings_menu():
    while True:
        os.system('cls')
        display_buy_settings_banner()
        choice = input("Please select an option you would like to change: ")
        if choice == '1':
            update_buy_setting("Raydium Slippage")
        elif choice == '2':
            update_buy_setting("Pump.fun Slippage")
        elif choice == '3':
            update_buy_setting("Raydium Prio Fee" + "in Lamports.")
        elif choice == '4':
            update_buy_setting("Pump.fun Prio Fee")
        elif choice == '5':
            update_buy_setting("RPC")
        elif choice == 'B'.lower():
            break
        else:
            print("Invalid choice. Please try again.")

def update_buy_setting(setting_name):
    new_value = input(f"Enter new value for {setting_name}: ").strip()
    if not os.path.exists(DATA_FILE) or os.stat(DATA_FILE).st_size == 0:
        data = {"tasks": [], "theme": "purplepink", "wallet": {}, "Raydium Fee": 0.05, "Raydium Slippage": 1000, "buy_settings": {"Pump.fun Slippage": "1000", "Pump.fun Prio Fee": "0.01", "RPC": "https://api.mainnet-beta.solana.com/"}}
    else:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
    if "buy_settings" not in data:
        data["buy_settings"] = {}
    data["buy_settings"][setting_name] = new_value
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f)
    print(f"{setting_name} updated successfully! Press any key to return to the menu.")
    input()

def display_buy_settings_banner():
    banner = """
  ██████╗  ██████╗ ████████╗██╗ ██████╗ ███╗   ██╗
  ██╔══██╗██╔═══██╗╚══██╔══╝██║██╔═══██╗████╗  ██║
  ██████╔╝██║   ██║   ██║   ██║██║   ██║██╔██╗ ██║
  ██╔═══╝ ██║   ██║   ██║   ██║██║   ██║██║╚██╗██║
  ██║     ╚██████╔╝   ██║   ██║╚██████╔╝██║ ╚████║ \033[0mBuy Settings
  ╚═╝      ╚═════╝    ╚═╝   ╚═╝ ╚═════╝ ╚═╝  ╚═══╝ \033[0mv1.0.1
                                                    
> \033[0m1 - Raydium Slippage
> \033[0m2 - Pump.fun Slippage
> \033[0m3 - Raydium Prio Fee
> \033[0m4 - Pump.fun Prio Fee
> \033[0m5 - RPC
> \033[0mB - Back
    """
    if os.path.exists(DATA_FILE) and os.stat(DATA_FILE).st_size != 0:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
        theme = data.get("theme", "purpleblue")
    else:
        theme = "purpleblue"

    theme_func = getattr(fade, theme)
    faded_banner = apply_theme(theme_func, banner)
    print(faded_banner.strip())

def change_theme():
    fade_options = ['purpleblue', 'greenblue', 'water', 'fire', 'pinkred', 'purplepink', 'brazil']
    print("Select a theme:")
    for idx, option in enumerate(fade_options):
        print(f"{idx + 1}. {option.capitalize()}")
    choice = int(input("Choose a theme: ").strip())
    if 1 <= choice <= len(fade_options):
        theme = fade_options[choice - 1]
        if os.path.exists(DATA_FILE) and os.stat(DATA_FILE).st_size != 0:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
        else:
            data = {"tasks": []}
        data["theme"] = theme
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f)
        print(f"Theme changed to {theme.capitalize()}.")
    else:
        print("Invalid choice. Please try again.")
    input("Press any key to return to the menu.")


def detect_contract_address(text):
    pattern = r"[A-HJ-NP-Za-km-z1-9]{32,44}"
    addresses = re.findall(pattern, text)
    return addresses

def main_menu(username):
    while True:
        os.system('cls')
        display_banner_with_fade()
        choice = input("Enter choice: ")
        if choice == '1':
            start_task(username)
        elif choice == '2':
            create_task()
        elif choice == '3':
            delete_task()
        elif choice == '4':
            configurations_menu()
        elif choice == 'B'.lower():
            exit()
        else:
            print("Invalid choice. Please try again.")

def apply_theme(theme_func, banner):
    return theme_func(banner)

def display_banner_with_fade():
    banner = f"""
  ██████╗  ██████╗ ████████╗██╗ ██████╗ ███╗   ██╗
  ██╔══██╗██╔═══██╗╚══██╔══╝██║██╔═══██╗████╗  ██║
  ██████╔╝██║   ██║   ██║   ██║██║   ██║██╔██╗ ██║
  ██╔═══╝ ██║   ██║   ██║   ██║██║   ██║██║╚██╗██║
  ██║     ╚██████╔╝   ██║   ██║╚██████╔╝██║ ╚████║
  ╚═╝      ╚═════╝    ╚═╝   ╚═╝ ╚═════╝ ╚═╝  ╚═══╝ \033[0mv1.0.1
                                                    
> \033[0m1 - Start Task
> \033[0m2 - Create Task
> \033[0m3 - Delete Task
> \033[0m4 - Settings
> \033[0mB - Exit
    """
    if os.path.exists(DATA_FILE) and os.stat(DATA_FILE).st_size != 0:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
        theme = data.get("theme", "purpleblue")
    else:
        theme = "purpleblue"

    theme_func = getattr(fade, theme)
    faded_banner = apply_theme(theme_func, banner)
    print(faded_banner.strip())

def display_configurations_banner():
    banner = """
  ██████╗  ██████╗ ████████╗██╗ ██████╗ ███╗   ██╗
  ██╔══██╗██╔═══██╗╚══██╔══╝██║██╔═══██╗████╗  ██║
  ██████╔╝██║   ██║   ██║   ██║██║   ██║██╔██╗ ██║
  ██╔═══╝ ██║   ██║   ██║   ██║██║   ██║██║╚██╗██║
  ██║     ╚██████╔╝   ██║   ██║╚██████╔╝██║ ╚████║ \033[0mSettings
  ╚═╝      ╚═════╝    ╚═╝   ╚═╝ ╚═════╝ ╚═╝  ╚═══╝ \033[0mv1.0.1
    """
    if os.path.exists(DATA_FILE) and os.stat(DATA_FILE).st_size != 0:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
        theme = data.get("theme", "purpleblue")
        wallet = data.get("wallet", {})
        if wallet:
            banner += f"\n> \033[0mCurrent Wallet Address: {wallet.get('walletPublicKey', 'None')}\n"
        else:
            banner += "\n> \033[0mCurrent Wallet Address: None generated\n"
    else:
        theme = "purpleblue"
        banner += "\n> \033[0mCurrent Wallet Address: None generated\n"

    banner += """
> \033[0m1 - Generate new wallet
> \033[0m2 - Export Private Key
> \033[0m3 - Change CLI Theme
> \033[0m4 - Buy Settings
> \033[0mB - Back to main menu
    """

    theme_func = getattr(fade, theme)
    faded_banner = apply_theme(theme_func, banner)
    print(faded_banner.strip())

def main():
    username = authenticate_with_keyauth()

    # Start the loading animation in a separate thread
    stop_event = threading.Event()
    loading_thread = threading.Thread(target=loading_animation, args=(stop_event,))
    loading_thread.start()

    try:
        sio.connect(f'http://162.33.177.57:8000', headers={'username': username})
    finally:
        stop_event.set()
        loading_thread.join()
        print("\rConnected to the backend                ")

    main_menu(username)
    sio.wait()

def loading_animation(stop_event):
    while not stop_event.is_set():
        for symbol in ['[/]', '[-]']:
            sys.stdout.write(f"\r{symbol} Connecting to server...")
            sys.stdout.flush()
            time.sleep(0.5)

def export_private_key():
    if not os.path.exists(DATA_FILE) or os.stat(DATA_FILE).st_size == 0:
        print("No wallet found. Generate a wallet first. Press any key to return to the menu.")
        input()
        return

    with open(DATA_FILE, 'r') as f:
        data = json.load(f)

    wallet = data.get("wallet", {})
    if wallet:
        print(f"Private Key: {wallet.get('privateKey', 'None')}")
    else:
        print("No wallet found. Generate a wallet first.")

    input("Press any key to return to the menu.")

if __name__ == "__main__":
    main()