import json
import time
from selenium import webdriver
from PokerNow import PokerClient

DATA_FILE = "game_data.json"

driver = webdriver.Chrome()
client = PokerClient(driver, cookie_path='cookie_file.pkl')

client.navigate('https://network.pokernow.club/sessions/new')
input("Complete the login process in the browser, then press enter to continue...")

client.cookie_manager.save_cookies()

# Navigate to the game table (replace with your specific game URL)
client.navigate('https://www.pokernow.club/games/pglHGhHrE341ZAczr_huXCuVb')
time.sleep(5)

print("Tracking game state using PokerNow API... Press Ctrl+C to stop.")

last_hand_data = None

def extract_game_data():
    """ Extracts relevant poker data using the PokerNow API. """
    
    # Retrieve the current game state
    game_state = client.game_state_manager.get_game_state()
    
    # Extract relevant information from the game state
    pot_size = game_state.pot_size
    community_cards = [str(card) for card in game_state.community_cards]
    
    players = []
    for player in game_state.players:
        players.append({
            "name": player.name,
            "stack": player.stack,
            "bet": player.bet_value,
            "cards": [str(card) for card in player.cards],
            "status": str(player.status),
            "hand_message": player.hand_message
        })

    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "pot_size": pot_size,
        "community_cards": community_cards,
        "players": players,
        "dealer_position": [str(card) for card in game_state.community_cards],
        "current_player": game_state.current_player,
        "blinds": game_state.blinds
    }


def save_hand_data(hand_data):
    """ Saves a hand to the JSON file in the desired format. """
    try:
        # Load existing hands data
        with open(DATA_FILE, "r") as file:
            existing_data = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        existing_data = []

    # Append the current hand data (if it's a new hand or state)
    existing_data.append(hand_data)

    # Save back to the JSON file
    with open(DATA_FILE, "w") as file:
        json.dump(existing_data, file, indent=4)

    print(f"Hand data saved: {hand_data['timestamp']} - Pot: {hand_data['pot_size']}")

def is_hand_complete(game_state):
    """ Determines if the hand is complete based on game state (e.g., by checking pot size, community cards, etc.). """
    # Example condition to detect if the hand is complete: check if the community cards are all revealed
    # Adjust this according to the actual logic of your game
    if game_state.winners:  # Assuming a hand is complete when there are winners
        return True
    if (len([str(card) for card in game_state.community_cards]) == 5):  # Assuming a hand is complete when there are 5 community cards
        return True
    active_players = [player for player in game_state.players if player.status != 'folded']
    if len(active_players) <= 1:  # Only one active player means hand is likely complete
        return True

    return False

def save_current_hand_if_complete():
    """ Checks if the current hand is complete and saves it. """
    global last_hand_data

    game_data = client.game_state_manager.get_game_state()
    
    # Check if hand is complete
    if is_hand_complete(game_data):
        # If it's a new hand or has changed significantly, save it
        if last_hand_data is None or game_data != last_hand_data:
            save_hand_data(game_data)
            last_hand_data = game_data  # Update the last saved hand data
        else:
            print("No new hand data to save. The hand seems to be ongoing.")
    else:
        print("Hand is not complete yet. Waiting for more data...")

try:
    while True:
        save_current_hand_if_complete()  # Check if the current hand is complete and save it
        time.sleep(5)  # Reduce API calls

except KeyboardInterrupt:
    print("\nGame tracking stopped by user.")

finally:
    driver.quit()
