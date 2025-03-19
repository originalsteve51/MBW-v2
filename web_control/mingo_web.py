# on branch web-view-2

from flask import Flask, render_template, render_template_string, request, jsonify, session, redirect, url_for, make_response
import os, json, logging
import time



# Create the Flask application
app = Flask(__name__)

# NOTE: The secret key is used to cryptographically-sign the cookies used for storing
#       the session data.
app.secret_key = 'MINGO_SECRET_KEY'

stop_requests = []

run_on_host = os.environ.get('RUN_ON_HOST') 
using_port = os.environ.get('USING_PORT')
update_interval = os.environ.get('MINGO_UPDATE_INTERVAL')
debug_mode = os.environ.get('MINGO_DEBUG_MODE')

print(f"run_on_host: {run_on_host}, Using Port: {using_port}, Update interval: {update_interval}, Debug: {debug_mode}")

songs = []
cards = {}
votes_required = None
number_of_players = 0
song_timeout = 0
refresh_screen = []
tapped_states_by_user = {}
game_selections_by_card = {}
initial_tapped_states = "[false,false,false,false,false,false,false,false,false,false,false,false,false,false,false,false,false,false,false,false,false,false,false,false,false]"

# List of card numbers that have claimed a win. Kept as a list
# to provide for the case where more than one card is claimed to be a winner.
win_claims = []
playlist_name = None

# List that is polled by cards...whenever it has ids they are
# pulled and removed from the session of the caller
sign_off_all_ids = []


# The tapped/untapped state of a player's game is kept in JavaScript persistent storage
# on the browser. This allows state to persist between screen refreshes in the case where
# a twitchy user refreshes the screen during game play. Without saved state, the state 
# of the game is lost when the page refresh occurs. 
# In JavaScript the localStorage feature is uses to store the state.
#
# reset_player_storage is an array of boolean that tells for each player/card number whether
# a GET request needs to reset the browser-side state for the user. This state is initially all
# untapped except for the center square. When a GET is issued for the card page, the flag 
# determines whether to use saved state or to wipe the board (and the state) to its starting
# untapped status.
active_player_ids = set()
offline_player_ids = set()
inactive_player_ids = set([0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29])
# inactive_player_ids = set([0])
reset_player_storage = [False for _ in range(len(inactive_player_ids))]
invalid_login = [True for _ in range(len(inactive_player_ids))]

lock_flag = False


@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin']='*'
    response.headers['Access-Control-Allow-Methods']='GET,POST,OPTIONS'
    response.headers['Access-Control-Allow-Headers']='Content-Type'
    return response

@app.route('/<int:player_id>', methods=['GET'])
def assign_player_id(player_id):
    global active_player_ids
    global inactive_player_ids
    global lock_flag
    
    if not lock_flag:
        if not player_id in active_player_ids and player_id in inactive_player_ids:
            print('Assigning player id', player_id)
            active_player_ids.add(player_id)
            inactive_player_ids.remove(player_id)
            update_validity_flags()

            return activate_player(player_id)

        else:
            return render_template('invalid_id.html', 
                                  player_id=player_id,
                                  run_on_host=run_on_host, 
                                  using_port=using_port)
    else:
        return render_template('game_is_locked.html', 
                            run_on_host=run_on_host, 
                            using_port=using_port)


def update_validity_flags():
    global active_player_ids
    global inactive_player_ids
    global invalid_login

    for _ in active_player_ids:
        try:
            invalid_login[_] = False
        except IndexError:
            invalid_login.append(False)

    for _ in inactive_player_ids:
        try:
            invalid_login[_] = True
        except IndexError:
            invalid_login.append(True)



@app.route('/rel', methods=['GET'])
def release_player_id():
    global active_player_ids
    global inactive_player_ids
    global reset_player_storage
    
    print('----------> In release_player_id()')
    release_id = 'Unknown Id'
    if 'player_id' in session:
        release_id = session['player_id']
        print(f'-------------> {release_id} is in session')
        if release_id in active_player_ids:
            active_player_ids.remove(release_id)
            inactive_player_ids.add(release_id)
            tapped_states_by_user[release_id] = initial_tapped_states
            print(f'-------------> {release_id} deactivated')
        
    
            
        session.pop('player_id', None)

        if 'player_id' in session:
            print('I thought player_id was removed from session, but NO!')
        else:
            print('Player id is not in session anymore')

        reset_player_storage[release_id] = True
        update_validity_flags()

        print(f'Released {release_id} for reuse and removed player_id from session')

    return render_template('released.html',
                            player_id=release_id,
                            run_on_host=run_on_host, 
                            using_port=using_port)
    
@app.route('/addOfflinePlayer', methods=['GET'])
def add_offline_player():
    global offline_player_ids
    global active_player_ids
    
    try:
        offline_player_id = min(inactive_player_ids)
    except ValueError:
        pass
    
    offline_player_ids.add(offline_player_id)
    active_player_ids.add(offline_player_id)
    inactive_player_ids.remove(offline_player_id)

    update_validity_flags()
    activate_player(offline_player_id, True)


    return redirect(url_for('admin'))

@app.route('/lockGame', methods=['GET'])
def lock_game():
    global lock_flag

    lock_flag = not lock_flag

    return redirect(url_for('admin'))
  

@app.route('/card', methods=['GET'])
def card():
    global cards
    global playlist_name
    global invalid_login

    if len(cards) == 0:
        keep_id = request.args.get('keep_id', default=False, type=bool)
        if not keep_id:
            session.pop('player_id', None)
        return redirect(url_for('not_ready'))

    try:
        card_number = session['player_id']
        
        if invalid_login[card_number]:
            session.pop('player_id', None)
            return key_error(None)
        
        reset_storage = reset_player_storage[card_number]
        reset_player_storage[card_number] = False
        
        try:
            titles = cards[str(card_number)]
        except KeyError:
            return key_error(None) 

        # print('========> ', playlist_name)
        return render_template('card_view.html', 
                                card_number=card_number, 
                                titles=titles,
                                stop_requests=stop_requests, 
                                run_on_host=run_on_host, 
                                using_port=using_port,
                                update_interval=update_interval,
                                playlist_name=playlist_name,
                                reset_storage=reset_storage)
    except KeyError:
        return key_error(None)


@app.route('/not_ready', methods=['GET'])
def not_ready():
    try:
        player_id = session['player_id']
    except KeyError:
        player_id = None
    return render_template('game_not_ready.html', 
                            player_id=player_id,
                            run_on_host=run_on_host, 
                            using_port=using_port)


def key_error(player_id):
    return render_template('invalid_id.html', 
                            player_id=player_id,
                            run_on_host=run_on_host, 
                            using_port=using_port)

@app.route('/saveTappedStates', methods=['POST'])
def save_tapped_states():
    global tapped_states_by_user

    # Save the tapped state info under the player id found in the current session
    data = request.get_json()
    tapped_states = data["tappedStates"]

    tapped_states_by_user[session['player_id']] = tapped_states
    
    # print('================= tapped states ', tapped_states_by_user)

    return jsonify()

@app.route('/getTappedStates', methods=['POST'])
def get_tapped_states():
    global tapped_states_by_user

    # Get the tapped state info under the player id in the request
    data = request.get_json()
    card_number = data["card_to_retrieve"]

    try:
        tapped_states_for_user = tapped_states_by_user[card_number]
        return jsonify({'states': tapped_states_for_user})
    except KeyError:
        return jsonify({'states': []})
    
@app.route('/save_game_selections', methods=['POST'])
def save_game_selections():
    selections = request.get_json()
    for key, value in selections.items():
        # print (f'------- >>>> key: {key}, value: {value}')
        game_selections_by_card[int(key)] = value
    # print('--------->>>>> ', game_selections_by_card)
    return jsonify()

@app.route('/get_game_selections', methods=['POST'])
def get_game_selections():
    global game_selections_by_card

    # Get the tapped state info under the player id in the request
    # data = request.get_json()
    # card_number = data["card_to_retrieve"]

    try:
        # tapped_states_for_user = tapped_states_by_user[card_number]
        return jsonify({'states': game_selections_by_card})
    except KeyError:
        return jsonify({'states': []})

@app.route('/claimWinner', methods=['POST'])
def claimWinner():
    global win_claims
    data = request.get_json()
    card_claiming_win = data["card_claiming_win"]
    # print("winner claim received from card number: ", card_claiming_win)
    # Add card claiming win to win_claims, the list of cards that need to be checked 
    # by the game engine.
    # The game engine polls this list to see if a check should be made
    # Duplicates are not allowed...
    if card_claiming_win not in win_claims:
        win_claims.append(card_claiming_win)
        # print('win_claims: ', win_claims)
    return jsonify({"status": "success", "received": card_claiming_win})

@app.route('/win_claims', methods=['GET', 'POST'])
def get_win_claims():
    global win_claims
    ret_json = jsonify({'win_claims': win_claims})
    # time.sleep(1)
    # print ("Returning win_claims: ", win_claims)

    # Clear the claims list
    win_claims.clear()
    return ret_json

@app.route('/game_misc_data', methods=['POST'])
def game_misc_data():
    global playlist_name
    global number_of_players
    global refresh_screen
    json_string = request.get_json()
    data = json.loads(json_string)
    playlist_name = data["playlist_name"]
    # print(f'Loaded cards for {playlist_name}')
    number_of_players = int(data["number_of_players"])
    refresh_flag = data["refresh_flag"]
    refresh_screen.clear()
    for _ in range(number_of_players):
        refresh_screen.append(refresh_flag)

    
    # Respond to the client
    return jsonify({"status": "success", "received": data})

@app.route('/clear_refresh', methods=['POST'])
def clear_refresh():
    global refresh_screen
    json_str = request.get_json()
    # print('==================================>>>> ', json_str)
    # data = json.loads(json_str)
    # print('==================================>>>> ', json_str["player_nbr"])
    # print("clear_refresh: ", json_string)
    player_nbr = json_str["player_nbr"]
    refresh_screen[int(player_nbr)] = False
    # print(f'Cleared refresh flag for: ', player_nbr)
    return jsonify({"status": "success", "received": "OK"})


@app.route('/admin', methods=['GET'])
def admin():
    global active_player_ids
    global offline_player_ids
    global inactive_player_ids
    global invalid_login
    global playlist_name
    
    response = make_response( render_template('admin.html',
                            lock_flag=lock_flag,
                            active_player_ids=active_player_ids,
                            offline_player_ids=offline_player_ids,
                            inactive_player_ids=inactive_player_ids,
                            playlist_name=playlist_name,
                            card_count=len(cards),
                            invalid_login=invalid_login,
                            run_on_host=run_on_host, 
                            using_port=using_port))

    # Set Cache-Control headers
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/unloadCards', methods=['GET','POST'])
def unload_cards():
    global cards
    global playlist_name
    cards.clear()
    playlist_name = None
    return redirect(url_for('admin'))

@app.route('/signOffAll', methods=['GET','POST'])
def sign_off_all():
    global active_player_ids
    global inactive_player_ids
    global reset_player_storage
    global invalid_login
    global tapped_states_by_user
    global game_selections_by_card
    global sign_off_all_ids
    global offline_player_ids

    reset_player_storage = [True for _ in range(len(reset_player_storage))]
    invalid_login = [True for _ in range(len(invalid_login))]
    

    # Load list that is polled by card pages, these ids are
    # removed from each card session
    sign_off_all_ids = [an_id for an_id in active_player_ids]

    for _ in range (len(active_player_ids)):
        player_id = active_player_ids.pop()
        inactive_player_ids.add(player_id)

    for _ in range (len(offline_player_ids)):
        player_id = offline_player_ids.pop()
        inactive_player_ids.add(player_id)

    tapped_states_by_user.clear()
    game_selections_by_card.clear()
    # cards.clear()
    

    return redirect(url_for('admin'))



# !!! TODO If the session already has 'player_id' in it then do not
#     permit rejoin with another id. First id must be released! Then join again.
@app.route('/join', methods=['GET'])
def join_game():
    global active_player_ids
    global inactive_player_ids
    global invalid_login
    remove_from_active = -1
    if not lock_flag:        
        if 'player_id' in session:
            # This user already has a player id. Handle an attempt to join again
            # by starting the player over with a new id. Return the current id to
            # the pool of available ids.
            player_id = session['player_id']
            session.pop('player_id', None)
            print('\n============> /join removed id from session', player_id)

            if player_id not in offline_player_ids:
                remove_from_active = player_id
                try:
                    active_player_ids.remove(remove_from_active)
                except KeyError:
                    print('\n========> /join KeyError', remove_from_active)
                inactive_player_ids.add(remove_from_active)

                # To remove the id from the session we have to return a page to
                # the browser. This is because the session is held on the browser,
                # so the removal of the player_id from the session requires a
                # response after popping the player_id on the server.
                return render_template('released.html',
                            player_id=remove_from_active,
                            run_on_host=run_on_host, 
                            using_port=using_port)

        if len(cards) == 0:
            return render_template('game_not_ready.html',
                                player_id='not assigned yet.', 
                                run_on_host=run_on_host, 
                                using_port=using_port)

        # We get here only when the player_id is not in the session. So we
        # start by picking an inactive id, putting it in the session, and activating it.
        if len(inactive_player_ids)>0:
            new_player_id = min(inactive_player_ids)
            inactive_player_ids.remove(new_player_id)
            print('\n=========> /join activated', new_player_id)
        else:
            new_player_id = max(active_player_ids)+1
            active_player_ids.add(new_player_id)
            invalid_login.append(False)
            reset_player_storage.append(False)
            print('\n=========> /join made new player_id', new_player_id)
                
        session['player_id'] = new_player_id
        print('\n============> /join added to session', new_player_id)

        update_validity_flags()
    
        return activate_player(new_player_id)
        

    else:
        return render_template('game_is_locked.html', 
                            run_on_host=run_on_host, 
                            using_port=using_port)
       
    



def activate_player(player_id, offline=False):        
    global active_player_ids
    global inactive_player_ids
    global invalid_login
    global reset_player_storage

    session['player_id'] = player_id
    try:
        reset_player_storage[player_id] = True
    except IndexError:
        reset_player_storage.append(True)
    invalid_login[player_id] = False

    try:
        tapped_states_by_user[player_id] = initial_tapped_states
    except IndexError:
        tapped_states_by_user.append(initial_tapped_states)

    active_player_ids.add(player_id)
    if player_id in inactive_player_ids:
        inactive_player_ids.remove(player_id)


    if not offline:
        if len(cards) != 0:
            return redirect(url_for('card'))
        else:
            return render_template('game_not_ready.html', 
                                    player_id=player_id, 
                                    run_on_host=run_on_host, 
                                    using_port=using_port)
    else:
        # Adding a player offline so let the caller handle the next
        # screen display
        pass


@app.route('/cards_clear', methods=['POST'])
def cards_clear():
    # global cards
    global songs 
    # print('=============>>> clearing songs')
    # cards.clear()
    songs.clear()
    return jsonify()


@app.route('/card_load', methods=['POST'])
def card_load():
    global cards
    global reset_player_storage

    reset_player_storage = [True for _ in range(len(reset_player_storage))]

    # Get the JSON data from the request
    json_string = request.get_json()
    # print("Received data:", data)
    # print (json_to_songs(data))
    # Parse the JSON string into a Python dictionary
    data = json.loads(json_string)

    # Get the card number
    card_nbr = data["card_nbr"]
    # print("Loading card number", card_nbr)

    # Extract the list of song titles
    # Start with an empty list
    songs.append([])
    songs_temp = [song["title"] for song in data["songs"]]
    for song in songs_temp:
        # print('adding ', song, ' ', card_nbr)
        songs[len(songs)-1].append(song)
    
    cards.update({str(card_nbr): songs[len(songs)-1]})

    # print('\n\n\n========= Loaded: ',str(card_nbr),'\n',cards[str(card_nbr)])

    if card_nbr == 1:
        card_debug()

    # Respond to the client
    return jsonify({"status": "success", "received": data})

@app.route('/set_votes_required', methods=['POST'])
def set_votes_required():
    global votes_required
    global song_timeout
    
    if request.method == 'POST':
        json_string = request.get_json()
        data = json.loads(json_string)
        # print("Received votes_required data:", data)
        votes_required = data["votes_required"]
        song_timeout = int(data['song_timeout'])
    
        return jsonify({'votes_required': 'OK'})    



@app.route('/clear', methods=['GET'])
def clear_stop_requests():
    if request.method == 'GET':
        stop_requests.clear()
        return render_template_string("""
            <h1>Stop requests have been cleared</h1>
        """)

@app.route('/check', methods=['GET'])
def check_status():
    if request.method == 'GET':
        player_id = session['player_id']
        # print('player id: ', player_id)
        return render_template_string("""
            <h1>Player id: {{player_id}}</h1>
        """, player_id=player_id)        

@app.route('/requeststop', methods=['POST'])
def add_stop_request():
    if request.method == 'POST':
        # Record the player's request to stop playing
        if (session['player_id'] not in stop_requests):
            stop_requests.append(session['player_id'])
        else:
            pass
            # print('not recording a repeated request')
        return jsonify({'stoprequests': stop_requests})


@app.route('/stopdata', methods=['GET', 'POST'])
def get_stop_data():
    return jsonify({'stoprequests': stop_requests, 
                    'votes_required': votes_required,
                    'song_timeout': song_timeout, 
                    'refresh_screen': refresh_screen})

@app.route('/submit', methods=['POST'])
def submit():
    data = request.get_json()
    if 'text' in data:
        text_value = data['text']
        return jsonify({'message': f'Text received: {text_value}'})
    else:
        return jsonify({'error': 'no text received'})

@app.route('/get_stop_count', methods=['GET'])
def get_stop_count():
    return str(len(stop_requests))

@app.route('/get_player_count', methods=['GET'])
def get_player_count():
    return str(len(active_player_ids))


@app.route('/debug', methods=['GET'])
def card_debug():
    return render_template('timeout.html')


if __name__ == '__main__':

    log = logging.getLogger('werkzeug')
    log.setLevel(logging.WARNING)
    debug_mode_bool = True
    if debug_mode == 'False':
        debug_mode_bool = False

    app.logger.warning('=============> Log level set')
    app.run(debug=debug_mode_bool, threaded=True, port=using_port, host='0.0.0.0')
#    app.run(debug=False, threaded=True, port=8080, host='127.0.0.1')
