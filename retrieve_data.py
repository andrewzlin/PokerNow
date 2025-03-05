import json
import time
import os
from selenium import webdriver
from PokerNow import PokerClient

DATA_FILE = "game_data.json"

driver = webdriver.Chrome()
client = PokerClient(driver, cookie_path='cookie_file.pkl')

client.navigate('https://network.pokernow.club/sessions/new')
input("Complete the login process in the browser, then press enter to continue...")

client.cookie_manager.save_cookies()

# Navigate to the game table (replace with your specific game URL)
client.navigate('https://www.pokernow.club/games/pglR_4hi883MBgE5gu9XB2c-U')
time.sleep(5)

print("Tracking game state using PokerNow API... Press Ctrl+C to stop.")

# Initialize tracking variables
last_hand_data = None
hand_actions = []
last_hand_id = None
last_saved_actions = []

def get_hand_id(hand_data):
    """Generate a unique ID for a hand based on timestamp and dealer position"""
    # Use the first action's timestamp if available (usually the new_hand action)
    if 'actions' in hand_data and hand_data['actions']:
        for action in hand_data['actions']:
            if action['type'] == 'new_hand':
                return f"{action['timestamp']}_{action['dealer']}"
    
    # Fallback to the hand's timestamp and dealer position
    return f"{hand_data['timestamp']}_{hand_data['dealer_position']}"

def extract_game_data():
    """ Extracts relevant poker data using the PokerNow API. """
    
    # Retrieve the current game state
    game_state = client.game_state_manager.get_game_state()
    
    # Extract information using the API methods
    community_cards = [str(card) for card in game_state.community_cards]
    
    players = []
    for player in game_state.players:
        player_data = {
            "name": player.name,
            "stack": player.stack,
            "bet": player.bet_value,
            "status": str(player.status)
        }
        
        # Only include cards if they're visible
        if hasattr(player, 'cards') and player.cards:
            player_data["cards"] = [str(card) for card in player.cards]
        else:
            player_data["cards"] = ["Unknown Card", "Unknown Card"]
            
        # Include hand message if available
        if hasattr(player, 'hand_message') and player.hand_message:
            player_data["hand_message"] = player.hand_message
            
        players.append(player_data)

    # Collect winners if available
    winners = []
    if hasattr(game_state, 'winners') and game_state.winners:
        for winner in game_state.winners:
            winner_data = {
                "name": winner['name'],
                "stack_info": winner['stack_info']
            }
            winners.append(winner_data)

    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "game_type": game_state.game_type if hasattr(game_state, 'game_type') else "",
        "pot_size": game_state.pot_size,
        "community_cards": community_cards,
        "players": players,
        "dealer_position": game_state.dealer_position,
        "current_player": game_state.current_player,
        "blinds": game_state.blinds,
        "winners": winners,
        "is_your_turn": game_state.is_your_turn if hasattr(game_state, 'is_your_turn') else False
    }

def extract_compact_hand_data(current_data, actions):
    """Extract only the essential information for a compact hand record"""
    
    # Determine the final stage based on community cards
    stage = "preflop"
    community_cards = current_data["community_cards"]
    if len(community_cards) == 3:
        stage = "flop"
    elif len(community_cards) == 4:
        stage = "turn"
    elif len(community_cards) == 5:
        stage = "river"
    
    # Create a compact hand record
    return {
        "timestamp": current_data["timestamp"],
        "game_type": current_data["game_type"],
        "blinds": current_data["blinds"],
        "dealer_position": current_data["dealer_position"],
        "pot_size": current_data["pot_size"],
        "community_cards": community_cards,
        "stage": stage,
        "players": current_data["players"],
        "actions": actions,
        "winners": current_data["winners"]
    }

def detect_new_actions(current_state, previous_state):
    """Detect actions by comparing current and previous game states"""
    actions = []
    
    # If no previous state, this is the start of tracking
    if not previous_state:
        return [{
            "type": "tracking_started",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }]
    
    # Check if the dealer position changed (new hand)
    if current_state.get("dealer_position") != previous_state.get("dealer_position"):
        actions.append({
            "type": "new_hand",
            "dealer": current_state.get("dealer_position"),
            "blinds": current_state.get("blinds"),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        })
    
    # Check for new community cards
    current_cards = current_state.get("community_cards", [])
    previous_cards = previous_state.get("community_cards", [])
    
    if len(current_cards) > len(previous_cards):
        # New cards were dealt
        new_cards = current_cards[len(previous_cards):]
        
        if len(current_cards) == 3:
            actions.append({
                "type": "flop",
                "cards": current_cards,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            })
        elif len(current_cards) == 4:
            actions.append({
                "type": "turn",
                "card": current_cards[3],
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            })
        elif len(current_cards) == 5:
            actions.append({
                "type": "river",
                "card": current_cards[4],
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            })
    
    # Check for player actions by comparing bets and statuses
    current_players = {p["name"]: p for p in current_state.get("players", [])}
    previous_players = {p["name"]: p for p in previous_state.get("players", [])}
    
    for name, current_player in current_players.items():
        if name in previous_players:
            prev_player = previous_players[name]
            
            # Check for fold
            if prev_player["status"] != "PlayerState.FOLDED" and current_player["status"] == "PlayerState.FOLDED":
                actions.append({
                    "type": "fold",
                    "player": name,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                })
            
            # Check for bet/raise/call
            if float(current_player["bet"] if current_player["bet"] else '0') > float(prev_player["bet"] if prev_player["bet"] else '0'):
                # Determine action type
                if float(prev_player["bet"] if prev_player["bet"] else '0') == 0:
                    action_type = "bet"
                else:
                    action_type = "raise"
                
                actions.append({
                    "type": action_type,
                    "player": name,
                    "amount": float(current_player["bet"] if current_player["bet"] else '0') - float(prev_player["bet"] if prev_player["bet"] else '0'),
                    "total_bet": current_player["bet"],
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                })
            
            # Check for check (bet remains 0)
            if prev_player["bet"] == "0" and current_player["bet"] == "0" and current_state.get("current_player") != name:
                # Only register check if it's no longer this player's turn
                actions.append({
                    "type": "check",
                    "player": name,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                })
    
    # Check for winners (hand completion)
    if current_state.get("winners") and not previous_state.get("winners"):
        for winner in current_state.get("winners", []):
            actions.append({
                "type": "win",
                "player": winner["name"],
                "stack_info": winner["stack_info"],
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            })
    
    return actions

def save_hand_data(hand_data):
    """ Saves a hand to the JSON file in the desired format. """
    # Only save hands with winners
    if not hand_data.get("winners"):
        print("Skipping hand without winner")
        return False
    
    # Load existing data if file exists
    all_hands = []
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                all_hands = json.load(f)
        except json.JSONDecodeError:
            all_hands = []
    
    # Add the new hand
    all_hands.append(hand_data)
    print(f"Added completed hand with winner: {hand_data['winners'][0]['name']}")
    
    # Write back to file
    with open(DATA_FILE, 'w') as f:
        json.dump(all_hands, f, indent=2)
    
    return True

def is_hand_complete(game_state):
    """ Determines if the hand is complete based on game state. """
    # Check if there are winners
    if hasattr(game_state, 'winners') and game_state.winners:
        return True
    
    # Check if all community cards are dealt (showdown)
    if len(game_state.community_cards) == 5:
        # Ensure betting is complete
        active_players = [p for p in game_state.players if p.status != 'FOLDED']
        if len(active_players) > 1:
            # Check if all active players have the same bet amount (betting round complete)
            bet_amounts = set(p.bet_value for p in active_players)
            if len(bet_amounts) == 1:
                return True
    
    # Check if only one player remains active
    active_players = [p for p in game_state.players if p.status != 'FOLDED']
    if len(active_players) <= 1:
        return True
    
    return False

def process_game_state():
    """ Processes the current game state, tracking actions and checking for hand completion. """
    global last_hand_data, hand_actions, last_hand_id
    
    # Get current game state
    game_state = client.game_state_manager.get_game_state()
    current_data = extract_game_data()
    
    # Detect new actions by comparing with last state
    if last_hand_data:
        new_actions = detect_new_actions(current_data, last_hand_data)
        if new_actions:
            # Add new actions to our tracking list
            hand_actions.extend(new_actions)
            for action in new_actions:
                print(f"Detected: {action['type']} - {action.get('player', '')}")
    
    # Check if this is a new hand starting
    new_hand_action = next((a for a in hand_actions if a.get("type") == "new_hand"), None)
    
    if new_hand_action and last_hand_id is None:
        # This is a new hand starting
        print("New hand detected")
        last_hand_id = f"{new_hand_action.get('timestamp')}_{new_hand_action.get('dealer')}"
    
    # Check if we have a winner (hand completed)
    has_winner = len(current_data.get("winners", [])) > 0
    
    # Only save data when we have a winner
    if has_winner:
        # Add hand completion status if not already present
        if not any(a.get("type") == "hand_complete" for a in hand_actions):
            hand_actions.append({
                "type": "hand_complete",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            })
        
        # Create compact version of the complete hand
        compact_hand = extract_compact_hand_data(current_data, hand_actions)
        
        # Check if this hand is already saved (avoid duplicates)
        should_save = True
        all_hands = []
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r') as f:
                    all_hands = json.load(f)
            except json.JSONDecodeError:
                all_hands = []
        
        # Simple check to avoid duplicates based on timestamp and dealer position
        for existing_hand in all_hands:
            # Check if this specific hand is already saved
            if (existing_hand.get("timestamp") == compact_hand.get("timestamp") and
                existing_hand.get("dealer_position") == compact_hand.get("dealer_position") and
                len(existing_hand.get("winners", [])) > 0):
                
                should_save = False
                print("Skipping save - this winning hand is already saved")
                break
        
        if should_save:
            # Save the hand data to file
            save_hand_data(compact_hand)
        
        # Reset for next hand
        hand_actions = []
        last_hand_id = None
    
    # Update last hand data
    last_hand_data = current_data

try:
    print("Starting poker game tracking. Press Ctrl+C to stop.")
    while True:
        process_game_state()
        time.sleep(2)  # Poll every 2 seconds

except KeyboardInterrupt:
    print("\nGame tracking stopped by user.")

finally:
    # Save any in-progress hand data before quitting
    if last_hand_data and hand_actions:
        # Make sure we have the hand completion marker
        if not any(a.get("type") == "hand_complete" for a in hand_actions):
            hand_actions.append({
                "type": "hand_complete",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            })
        
        compact_hand = extract_compact_hand_data(last_hand_data, hand_actions)
        save_hand_data(compact_hand)
        print("Final hand data saved before exit.")
    
    driver.quit()