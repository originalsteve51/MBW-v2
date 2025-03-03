"""
MIT License

Copyright (c) 2021, 2025 Stephen Harding

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


import os
import random
import cmd
import webbrowser

import csv
import math
import sys
from sys import stdout
from pathlib import Path
import pickle

import threading
import time
import requests

import qrcode
import json

import spotipy
from spotipy.oauth2 import SpotifyOAuth

#-----------------------------------
# A few global settings follow below
# @TODO Get rid of global values
#-----------------------------------
gridsize = 5
stepping = 16
save_path = './.cards.html'
input_file = './.mingo_input.csv'
current_dir = os.getcwd()
game_state_pathname = './.game_state.bin'



#-----------------------------------------------------------
# Spotify is a class that provides access to the Spotify API
# The spotipy library performs its magic here by using values
# found in the environment to authenticate the user. Once
# authenticated, the api can be called.
# This depends on the following environment variable values, which
# should be set by a shell script.
# export SPOTIPY_CLIENT_ID=
# export SPOTIPY_CLIENT_SECRET=
# export SPOTIPY_REDIRECT_URI="http://127.0.0.1:8080"
#-----------------------------------------------------------
class Spotify():
    def __init__(self):
        ascope = 'user-read-currently-playing,\
                playlist-modify-private,\
                user-read-playback-state,\
                user-modify-playback-state'
        ccm=SpotifyOAuth(scope=ascope, open_browser=True)
        self.sp = spotipy.Spotify(client_credentials_manager=ccm)

        # print(dir(self.sp))

#-------------------------------------------------------------------
# Playlist class
#-------------------------------------------------------------------
class Playlist():
    def __init__(self, sp):
        self.sp = sp
        self.track_set = set(())

    def get_playlists(self):
        results = self.sp.current_user_playlists(limit=50)
        lists = {}
        for i, item in enumerate(results['items']):
            lists[str(i)] = [item['name'], item['id']]
        return lists

    def duplicate_detect(self, track_name):
        is_duplicate = False
        if track_name in self.track_set:
            is_duplicate = True
        else:
            self.track_set.add(track_name)
        return is_duplicate

    def duplicate_detect_reset(self):
        self.track_set.clear()

    def playlist_processing(self, pl_id, m_writer=None):
        offset = 0
        while True:
            response = self.sp.playlist_items(pl_id,
                                        offset=offset,
                                        fields='items.track.name, items.track.id, items.track.artists.name, total',
                                        additional_types=['track'])

            if len(response['items']) == 0:
                break

            # Clear out duplicate detect before using it, otherwise
            # it holds previous usage data
            self.duplicate_detect_reset()

            for idx in range(0, len(response['items'])):
                track = response['items'][idx]['track']
                artist_name = response['items'][idx]['track']['artists'][0]['name']
                if not self.duplicate_detect(track['name']):
                    # track_id = track['id']
                    # track_urn = f'spotify:track:{track_id}'
                    # track_info = sp.track(track_urn)
                    # artist_name = track_info['album']['artists'][0]['name']
                    # print(track['name'], track['id'], artist_name)
                    if m_writer:
                        m_writer.writerow([idx+offset, idx+offset, track['name'], track['id'], artist_name])
                else:
                    print(f"The track named {track['name']} by {artist_name} was not used because its name is very similar to another track already used.")
            offset = offset + len(response['items']) 

            print(f'Processed {offset} records so far...')
        print(f'Total number of records processed: {offset}')


    def process_playlist(self, pl_index, save_to_file):
        playlist = self.get_playlists()[f"{pl_index}"]
        print(f'{playlist[0]}')
        pl_id = f'spotify:playlist:{playlist[1]}'

        if save_to_file:
            with open(input_file, mode='w') as mingo_file:
                m_writer = csv.writer(mingo_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
                m_writer.writerow([f'{playlist[0]}', 'track name', 'track id'])
                self.playlist_processing(pl_id, m_writer)
        else:
            self.playlist_processing(pl_id)

#-------------------------------------------------------------------
# Player class
#-------------------------------------------------------------------
class Player():
    def __init__(self, sp):
        self.active_player = None
        self.sp = sp

    def show_available_players(self, list_all_players=True):
        res = self.sp.devices()
        player_count = len(res['devices'])
        print(f'Your account is associated with {player_count} players.')
        for idx in range(player_count):
            if list_all_players:
                player_data = f"{res['devices'][idx]['name']},{res['devices'][idx]['type']}"
                active_msg = 'Inactive'
                if res['devices'][idx]['is_active']:
                    active_msg = 'Active'
                print(f'{idx}: {player_data}, {active_msg}')
            if res['devices'][idx]['is_active']: # and self.active_player is None:
                self.active_player = res['devices'][idx]['id']
                print(f'Selected active music player: ', {res['devices'][idx]['name']})

    def play_track(self, track_id):
        try:
            # Set the repeat mode to off, otherwise the track will repeat
            # and this is not what I think we want. Tracks should just
            # play once for MINGO
            self.sp.repeat(state='off', device_id=self.active_player)
            self.sp.start_playback(uris=[f'spotify:track:{track_id}'], 
                            device_id=self.active_player)
        except Exception as e:
            display_player_exception(e)

    def resume_track(self, track_id, position_ms):
        try:
            self.sp.start_playback(uris=[f'spotify:track:{track_id}'], 
                            device_id=self.active_player, 
                            position_ms=position_ms)
        except Exception as e:
            display_player_exception(e)

    def set_volume(self, volume_pct):
        self.sp.volume(volume_pct)

    def pause_playback(self):
        self.sp.pause_playback()


#-------------------------------------------------------------------
# Card class
#-------------------------------------------------------------------
class Card():
    def __init__(self, sheet, playlist_name, game_monitor, card_title_idxes):
        # sheet is a 25 element list with 24 track numbers and a url. These
        # represent 5 x 5 element rows of the Mingo board. The center element
        # is the url, which represents a free square.
        self.sheet = sheet
        self.playlist_name = playlist_name
        self.monitor = game_monitor

        # @todo When a Card is made, take all the track_ids that are listed on its sheet and
        # add them to the set unplayed_tracks. This way only the track_ids that are on cards
        # are played during the game. Originally I played all tracks, not just the ones on cards.
        # That causes the game to be too long in many cases.
        # !!! unplayed_tracks will be property of Game, but for now just test it here
        self.unplayed_tracks = set()
        print(card_title_idxes)

    def as_json(self, card_nbr):
        return songs_to_json(self.sheet, card_nbr)
        
    def as_html(self, f=stdout, readable=True):
        if readable:
            newline = '\n'
        else:
            newline = ''
        f.write("<table>"+newline)
        f.write("<tr>"+newline)
        bingo = ["<th>{}</th>".format(l) for l in list('MINGO')]
        for th in bingo:
            f.write(th)
        f.write("</tr>"+newline)
        for r in range(gridsize):
            f.write("<tr>"+newline)
            for c in range(gridsize):
                cell = r * gridsize + c
                cell = self.sheet[cell]
                been_played = self.monitor.has_been_played(cell)
                # Check length of cell string. apply a smaller fontsize if it's
                # too long, this tries to keep a card short enough to fit on a page
                # without running to the top of the next page.
                cell_class = ''
                if cell.startswith('<img'):
                    # Center cell is an image, always selected
                    cell_class = 'class="selected"'
                elif len(cell) > 25:
                    if been_played:
                        cell_class = 'class="long-text-cell-selected"'
                    else:
                        cell_class = 'class="long-text-cell"'
                elif been_played:
                    cell_class = 'class="selected"'


                cell_string = f'<td {cell_class}>' + cell + "</td>" + newline

                f.write(cell_string)
            f.write("</tr>\n")
        f.write("</table>"+newline)

    def as_array(self):
        selection_array = []
        for r in range(gridsize):
            
            for c in range(gridsize):
                cell = r * gridsize + c
                cell = self.sheet[cell]
                been_played = self.monitor.has_been_played(cell)
                # Check length of cell string. apply a smaller fontsize if it's
                # too long, this tries to keep a card short enough to fit on a page
                # without running to the top of the next page.
                if been_played:
                    selection_array.append(True)
                else:
                    selection_array.append(False)

        return selection_array

    def view_html(self):
        filename = 'file://'+current_dir+'/.cards.html'
        webbrowser.open_new_tab(filename)

def songs_to_json(song_titles, card_nbr):
    """
    Converts a list of song titles into a JSON string.

    Args:
        song_titles (list): A list of song titles (strings).

    Returns:
        str: A JSON string representation of the song titles.
    """
    if len(song_titles) != 25:
        raise ValueError("The list must contain exactly 25 song titles.")
    
    # Create a dictionary to structure the data
    print("===================================")
    print("processing card number: ", card_nbr)
    data = {"card_nbr": card_nbr, "songs": [{"id": i + 1, "title": title} for i, title in enumerate(song_titles)]}
    ret_json = json.dumps(data)
    print("===================================")
    
    # Convert the dictionary to a JSON string
    return ret_json # , indent=4)




class QRCodeGenerator():
    def __init__(self, base_url) -> None:
        self._save_path = '.'
        self._base_url = base_url

    def make_code(self, code_number):
        # Create a QR code object with the URL
        qr = qrcode.make(self._base_url+'/'+str(code_number))

        # Save the QR code image with a filename based on the URL
        # Removing special characters from the URL to create a clean filename
        filename = self._base_url.replace("https://", "").replace("http://", "").replace("/", "_").replace(":", "") +str(code_number)+ ".png"
        qr.save(filename, scale=2)

        return(filename)          


#-------------------------------------------------------------------
# CardFactory class
#-------------------------------------------------------------------
class CardFactory():
    def __init__(self, input_file, game_monitor) -> None:
        self.center_figure = '<img src="center-img-small.png"/>'
        self.qr_generator = QRCodeGenerator('http://svpserver5.ddns.net:8080/')
        self.input_titles = []
        self.input_ids = []
        self.input_track_ids = []
        self.input_artists = []
        self.game_monitor = game_monitor

        self.active_indexes = set();

        with open(input_file, 'r') as f:
            r = csv.reader(f, delimiter=',', quotechar='"')
            playlist_name_row = next(r)
            self.playlist_name = playlist_name_row[0]
            for row in r:
                self.input_artists.append(row[4])
                self.input_track_ids.append(row[3])
                # Shorten title by removing stuff after a hyphen that is preceded by
                # a space. Spotify titles often include meta-info like when a song
                # was remastered, and we don't want this on the game card. They seem
                # to always delimit the meta-info with a space-hyphen-space pattern. Some
                # song titles include hyphens, but they typically are not preceded
                # with a space.
                short_title = row[2].split(' - ', 1)[0]
                self.input_titles.append(short_title)
                self.input_ids.append(row[1])

        self.n_titles = len(self.input_titles)

        ## !!!
        self.title_idx = []
        ## !!!

        self.titles = []
        self.track_ids = []
        self.track_info = dict()
        for i, w in enumerate(self.input_titles):
            # print("CardFactory: "+str(i)+"...."+w)
            ## !!!
            self.title_idx.append(i)
            ## !!!
            self.titles.append(f'{w}')
            self.track_ids.append(self.input_track_ids[i])
            self.track_info[i] = f'{w}'



    def make_card(self, card_nbr):
        # print('Creating mingo card from: ' + str(len(self.titles)) + ' song titles')

        ## The random sample below needs to contain unique selections, never any duplicates.
        ## random.sample is supposed to provide unique selections, so use it...
        
        ## !!!
        card_title_idxes = random.sample(self.title_idx, gridsize**2 - 1)

        ## Add each card's indexes to the set of indexes used when we play
        self.active_indexes.update(card_title_idxes)
        
        sheet = []
        for idx in card_title_idxes:
            ## print(str(idx), self.titles[idx])
            sheet.append(self.titles[idx])
        ## !!!

        ## sheet = random.sample(self.titles, gridsize**2 - 1)
        qr_file_name = self.qr_generator.make_code(card_nbr)
        center_figure = '<img src="'+qr_file_name+'"'+'/>'
        # print(center_figure)
        sheet.insert(math.ceil(len(sheet)/2), center_figure) 
        return Card(sheet, self.playlist_name, self.game_monitor, card_title_idxes)

    def get_track_ids(self):
        return self.track_ids

    def get_active_indexes(self):
        return self.active_indexes

               
#-------------------------------------------------------------------
# Game class
#-------------------------------------------------------------------
class Game():
    def __init__(self, n_cards, sp, musicplayer):
        self.n_cards = n_cards
        self.sp = sp
        self.game_monitor = GameMonitor()

        self.testval = '555'

        card_factory = CardFactory(input_file, self.game_monitor)
        self.playlist_name = card_factory.playlist_name
        self.cards = dict()
        for card_nbr in range(n_cards):
            self.cards[card_nbr] = card_factory.make_card(card_nbr)

        self.active_indexes = card_factory.get_active_indexes(); ## !!!
        # print("Active indexes: " , self.active_indexes)
        
        self.track_ids = card_factory.get_track_ids()
        self.track_info = card_factory.track_info
        self.track_artists = card_factory.input_artists
        self.player = musicplayer

        self.played_tracks = []

        # unplayed_tracks needs to be a list so random.select will work. The active_indexes
        # is a set of all songs on all cards. Make the list now...
        self.unplayed_tracks = list(self.active_indexes)
        self.state = []
        
        self.paused_at_ms = None
        self.current_track_idx = None

        # @todo only add the tracks that are on cards to unplayed_tracks
        ## for idx in range(len(self.track_ids)):
        ##    self.unplayed_tracks.append(idx)

        # self.game_monitor.set_total_tracks(len(self.track_ids))
        self.game_monitor.set_total_tracks(len(self.unplayed_tracks))

        print(f'Created a Mingo game with {n_cards} cards')

    def get_testval(self):
        return self.testval

    def write_game_state(self):
        path = Path(game_state_pathname)
        with open(path, 'wb') as fp:
            pickle.dump(self, fp)

    def save_game_state(self, save_number):
        save_state_pathname = './.saved_game_'+save_number+'.bin'
        path = Path(save_state_pathname)
        with open(path, 'wb') as fp:
            pickle.dump(self, fp)
        print(f'Saved game to path {save_state_pathname}')

    def get_card(self, card_num):
        if card_num > self.n_cards-1 or card_num < 0:
            raise Exception(f'There are {self.n_cards} cards in this game, \
numbered 0 through {self.n_cards - 1}. Try again.')
        else:
            return self.cards[card_num] 

    def play_previous_track(self, back_index):
        """
        if back_index:
            play_index = int(back_index)
        else:
            play_index = -1
        """
        play_index = int(back_index)
        # print ('+++ number of played tracks: ', len(self.played_tracks))
        if play_index < len(self.played_tracks):
            track_idx = self.played_tracks[play_index]
            print("Playing track idx: ",track_idx)
            now_playing = self.track_info[track_idx]
            artist = self.track_artists[track_idx]
            self.current_track_idx = track_idx
            print(f'\nNow playing: "{now_playing}" by "{artist}"\n')
            track_to_play = self.track_ids[track_idx]
            self.player.play_track(track_to_play)
        else:
            print('Invalid request to play that track.')
        


    def play_next_track(self, testmode=False):
        if len(self.unplayed_tracks) == 0:
            print('The game is over. All tracks have been played.')
            return

        track_idx = random.choice(self.unplayed_tracks)
        self.unplayed_tracks.remove(track_idx)
        self.played_tracks.append(track_idx)
        print("Playing track idx: ",track_idx)
        
        now_playing = self.track_info[track_idx]
        artist = self.track_artists[track_idx]
        self.current_track_idx = track_idx
        self.game_monitor.add_to_played_tracks(now_playing)

        print(f'\nNow playing: "{now_playing}" by "{artist}"\n')
        track_to_play = self.track_ids[track_idx]
        if not testmode:
            self.player.play_track(track_to_play)

    def pause(self):
        self.player.pause_playback()
        self.paused_at_ms = self.currently_playing()[0]

    def resume(self):
        if self.paused_at_ms:
            track_to_resume = self.track_ids[self.current_track_idx]
            self.player.resume_track(track_to_resume, self.paused_at_ms)
            self.paused_at_ms = None
        else:
            print('Nothing was paused, so cannot resume!')


    def currently_playing(self):
        track = self.sp.current_user_playing_track()
        is_playing = False
        progress = 0
        if track:
            is_playing = track['is_playing']
            progress = track['progress_ms']
        return progress, is_playing

    def post_selections_to_web(self):
        selections = dict()
        for card_nbr in range(self.n_cards):
            card = self.get_card(card_nbr)
            selections[card_nbr] = card.as_array()
        requests.post(web_controller_url+'/save_game_selections',
                            json=selections)




    def view_in_browser(self, card_num=None):
        '''
        Renders a mingo card using html, saves the html to a file, and shows it in the default browser.

            parameters:
                card_num: The index of a mingo card to render. If None, show all cards.

            returns:
                None
        '''
        try:
            with open(save_path, 'w') as f:
                f.write("<html>")

                # First write a css that provides a good table rendering for mingo cards.
                # This also will cause one card per page when printing the browser
                # display of the cards.
                f.write("""
                <head>
                    <style>
                        td {
                            width: 120px;
                            height: 50px;
                            padding: 2px;
                            overflow: hidden;
                            text-align: center;
                            vertical-align: middle;
                            border: 1px solid black;
                            font-size: 18pt;
                            font-family: Arial, Helvetica, sans-serif;
                        }
                        .long-text-cell {
                            font-size: 12pt;
                        }
                        .long-text-cell-selected {
                            font-size: 12pt;
                            background: lightcoral;
                        }
                        .selected {
                            background: lightcoral;
                        }
                        img {
                            max-height: 50px;
                        }
                        br.space{
                            margin-top: 70px;
                        }

                        
                        @media print{
                            br.page{
                                page-break-before: always;
                            }
                        }
                        

                    </style>
                </head>
                <body>
                """)
                if not card_num:
                    for i in range(self.n_cards):
                        # Following prints one card per page. The css 'page' provides
                        # a page-break when printed. But this only actually works
                        # with Firefox, according to my testing. So use Firefox with
                        # this program.
                        card = self.get_card(i)
                        f.write(f"<h3>{card.playlist_name}, Card number {i}  </h3>")
                        card.as_html(f, False)
                        f.write("<br class='page'/>")
                        """
                        # Following prints two cards per page. This needs a very small
                        # font that old people like me cannot see well.
                        if (i+1) % 2 == 0:
                            f.write("<br class='page'/>")
                        else:
                            f.write("<br class='space'/>")
                        """
                else:
                    card = self.get_card(int(card_num))
                    f.write(f"<h3>{card.playlist_name}, Card number {card_num} </h3>")
                    card.as_html(f, False)
                    f.write("<br class='page'/>")

                    # For testing only...
                    # card.as_array()
                    # card.as_json(card_num)

                f.write("\n")

            filename = 'file://'+current_dir+'/.cards.html'
            browser = webbrowser.get('firefox')
            browser.open(filename)
            # The call below was originally used. It opened the cards in the default browser,
            # which is Chrome on my machine. 
            # But Chrome has problems with the css print definition
            # for br.page that is used to insert a page break when printing. Firefox works, so
            # I needed to specify non-default browser firefox as seen above...
            # @TODO Remove Firefox and test to see what happens.
            #webbrowser.open_new_tab(filename)
        except Exception as error:
            # @TODO Untested below. I think if I remove Firefox I will get an exception.
            # The line of code below will use the default browser in the absence of Firefox,
            # I think. I should check the specific exception and only display the default
            # browser when Firefox is not available. Then I should inform the user that
            # Firefox should be made available.
            webbrowser.open_new_tab(filename)
            print(error)


#-------------------------------------------------------------------
# ExitCmdException class - Just so we have a good name when breaking
# out of the command loop with an Exception
#-------------------------------------------------------------------
class ExitCmdException(Exception):
    pass 

#-------------------------------------------------------------------
# GameMonitor class - What's been played so far
#-------------------------------------------------------------------
class GameMonitor():
    def __init__(self):
        self.played_track_names = list()
        self.num_total_tracks = 0

    def add_to_played_tracks(self, track_name):
        self.played_track_names.append(track_name)

    def set_total_tracks(self, num_total_tracks):
        self.num_total_tracks = num_total_tracks

    def has_been_played(self, track_name):
        if track_name in self.played_track_names:
            return True
        else:
            return False

    def show_played_tracks(self, active_game, replay_track, cmd_processor):
        num_played = len(self.played_track_names)
        num_remaining = self.num_total_tracks - num_played

        if len(self.played_track_names) > 0:
            print('\nList of tracks played so far:')
            for (i, track_name) in enumerate(self.played_track_names, start=0):
                print(f'{i}\t{track_name}')

            print(f'\n{num_played} tracks have been played, \
{num_remaining} tracks are left to play.\n')

            if replay_track:
                print('+++ request to replay a track: ',replay_track)
                replay_index = int(replay_track)
                if replay_index < num_played + 1 and replay_index >= 0:
                    if active_game:
                        replay_index = replay_index
                        print (f'Replay index: {replay_index}')
                        active_game.play_previous_track(replay_index) # was -1

                        # Since we are playing another track, clear out the
                        # votes that may have been cast to skip
                        clear_web_votes(cmd_processor)

                    else:
                        print('There is not an active game.')
                else:
                    print(f'You made an invalid request to replay track {replay_index}.')
            
        else:
            print('\nNo tracks have been played yet.\n')

web_controller_url = os.environ['WEB_CONTROLLER_URL']
print('Web controller url: ', web_controller_url)
# web_controller_url = 'http://svpserver5.ddns.net:8080'
# web_controller_url = 'http://localhost:8080'
class WebMonitor():
    def __init__(self, cmdprocessor, trigger_vote_count):
        self._running = False
        self._thread = None
        self._cmdprocessor = cmdprocessor
        self._trigger_vote_count = int(trigger_vote_count)
        self._voting_allowed = True

    def start(self):
        if not self._running:
            # clear all stop requests before running the monitor
            # otherwise 'old' stop requests can cause a track to start
            # and stop immediately
            requests.get(web_controller_url+'/clear')
            print('trying to start WebMonitor')
            self._running = True
            self._voting_allowed = True
            self._thread = threading.Thread(target=self._run)
            self._thread.start()
            print('should be started')

    
    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join()

    def no_voting(self):
        self._voting_allowed = False
    
    def voting(self):
        self._voting_allowed = True

    def _run(self):
        while self._running:
            # print('inside running')
            if self._voting_allowed:
                stop_count = int(requests.get(web_controller_url+'/get_stop_count').content)
            else:
                stop_count = 0
            win_claims_json = requests.get(web_controller_url+'/win_claims')
            win_claims = win_claims_json.json()["win_claims"]
            # print(f"Claims : {win_claims}, length is {str(len(win_claims))}")
            claim_idx = 0
            while len(win_claims) > 0:
                card_to_check = win_claims[claim_idx]
                # print(f"Processing claim for card {win_claims[claim_idx]}")
                win_claims.remove(win_claims[claim_idx])
                # print(f"There are {len(win_claims)} items in claim list")
                # self._cmdprocessor.do_pause(self._cmdprocessor)
                self._cmdprocessor.do_view(card_to_check)
            
            # print(stop_count)
            if (self._voting_allowed and stop_count>=self._trigger_vote_count):
                requests.get(web_controller_url+'/clear')
                self._cmdprocessor.do_nexttrack(self._cmdprocessor)
            time.sleep(1)




#-------------------------------------------------------------------
# CommandProcessor class - Define the command language here. This
# extends the Python Cmd class, which brilliantly handles keyboard
# input by recognizing commands and dispatching them.
#-------------------------------------------------------------------
class CommandProcessor(cmd.Cmd):
    prompt = '\033[97m(No active game'
    # '\033[97m(Issue a command)\033[0m'
    auto_cmd = ''
    end_highlight='\033[0m'
    def __init__(self):
        super(CommandProcessor, self).__init__()
        self.active_game = None
        spotify = Spotify()
        self.sp = spotify.sp
        self.pl = Playlist(spotify.sp)
        self.player = Player(spotify.sp)

        # Start by displaying the available playlists
        self.do_playlists()

        self.web_monitor = None 

    def do_countplayers(self, _):
        player_count = int(requests.get(web_controller_url+'/get_player_count').content)
        print(f'There are {player_count} active players.')

    def do_newgame(self, options):
        self.do_makegame(options)
        self.do_webload(None)



    def do_webload(self, _):
        if self.active_game:
            print(f'Loading {self.active_game.n_cards} cards made from {self.active_game.playlist_name} to web controller')
            for card_nbr in range(self.active_game.n_cards):
                requests.post(web_controller_url+'/card_load',
                                json=self.active_game.cards[card_nbr].as_json(card_nbr))

            misc_data = {"playlist_name": self.active_game.playlist_name, 
                        "number_of_players": str(self.active_game.n_cards),
                        "refresh_flag": True}

            requests.post(web_controller_url+'/game_misc_data',
                                json=json.dumps(misc_data))
        else:
            print('There is not an active game. Create one using "makegame" and try again.')  

    def do_webunload(self, _):
        if self.active_game:
            print(f'Unloading {self.active_game.n_cards} cards made from web controller')

            # Make an empty card for each player
            for card_nbr in range(self.active_game.n_cards):
                empty_card = empty_card_json(card_nbr)
                requests.post(web_controller_url+'/card_load',
                                json=empty_card)

            misc_data = {"playlist_name": self.active_game.playlist_name, 
                        "number_of_players": str(self.active_game.n_cards),
                                "refresh_flag": True}

            requests.post(web_controller_url+'/game_misc_data',
                                json=json.dumps(misc_data))
        else:
            print('There is not an active game. Create one using "makegame" and try again.')  

    def do_auto(self, next_trigger_votes):
            self.auto_cmd = f':auto {next_trigger_votes})'
            if self.active_game:
                self.prompt = f'\033[97m({self.active_game.playlist_name}'+self.auto_cmd+self.end_highlight
            else:
                self.prompt = f'\033[97m(No Active Game'+self.auto_cmd+self.end_highlight

            if next_trigger_votes and int(next_trigger_votes) > 0:
                # Non-zero voting is enabled. Tell the web monitor to watch for votes.
                self.web_monitor.voting()


                # Only start the web monitor thread once (a singleton)
                # If there are multiple monitor threads, songs will be skipped
                if not self.web_monitor:
                    self.web_monitor = WebMonitor(self, next_trigger_votes)
                    print('The Web Monitor has been started. Next song triggers when ',next_trigger_votes, ' are received')      
                    
                    self.web_monitor.start()
                    
                    # Use the value of progress > 0 to determine when the nexttrack should
                    # start automatically
                    # progress = self.active_game.currently_playing()[0]
                else:
                    print(f'Changing the number of votes to change song from {str(self.web_monitor._trigger_vote_count)} to {next_trigger_votes}.')                    
                    self.web_monitor._trigger_vote_count = int(next_trigger_votes)
                    if self.web_monitor._running:
                        print('The Web Monitor was started previously.')
                    else:
                        print('Starting the Web Monitor.')
                        self.web_monitor.start()
                
                # Send next_trigger_votes to web controller so it will update
                # this on each user screen
                votes_required = {"votes_required": next_trigger_votes}
                requests.post(web_controller_url+'/set_votes_required',
                                    json=json.dumps(votes_required))

            elif next_trigger_votes and int(next_trigger_votes) <= 0:
                if next_trigger_votes == 0:
                    print('Zero trigger votes')
                else:
                    print(f'{next_trigger_votes} requested')

                # Send the zero to the web controller to block further voting
                # and to update the info on each user screen
                votes_required = {"votes_required": next_trigger_votes}
                requests.post(web_controller_url+'/set_votes_required',
                                    json=json.dumps(votes_required))

                # Even when not voting we want the 'Winner' button to work, so
                # start the monitor if not running already to keep track of Winner claims.
                if not self.web_monitor:
                    self.web_monitor = WebMonitor(self, next_trigger_votes)

                # if self.web_monitor:
                    print('No more voting via the Web Monitor.')      
                    self.web_monitor.start()
                    self.web_monitor.no_voting()
            else:
                print('You must enter the number of votes that will cause the next song to play')    


    """Process commands related to Spotify playlist management for the game of MINGO """
    def do_playlists(self, sub_command=None):
        """Display all Spotify playlists for the authorized Spotify user."""
        playlists = self.pl.get_playlists()
        print('\nThese are your playlists:')
        for k in playlists.keys():
            print(f'{k}: {playlists[f"{k}"][0]}')
        print('\nIssue the ''makegame'' command followed by a playlist number to start a new game, \
or issue the ''continuegame'' command to restart an old game.')
    
    def do_showlist(self, list_number):
        """Show the names of tracks in a Spotify playlist."""
        if list_number:
            self.pl.process_playlist(list_number, False)
        else:
            print('You must enter the number of a playlist to show its tracks')
    
    def do_userinfo(self, line):
        """Show the name of the signed-on Spotify user whose playlists are to be used to generate Mingo games."""
        print(self.pl.sp.me()['display_name'])

    def do_makegame(self, options):
        """Use the currently active playlist to generate a specified number of Mingo cards."""
        num_cards = 10
        playlist_num = -1
        if not options:
            print('You did not enter a playlist number to use for this game. Try again.')
            return
        else:
            arg_list = options.split(' ')
            if len(arg_list) == 1:
                playlist_num = int(arg_list[0])
            elif len(arg_list) == 2:
                playlist_num = int(arg_list[0])
                num_cards = int(arg_list[1])
            
            self.pl.process_playlist(playlist_num, True)
            requests.get(web_controller_url+'/signOffAll')

        try:
            self.active_game = Game(num_cards, self.sp, self.player)

            # Save the game state before any songs are played. Then if the
            # user quits immediately, the unplayed game can be continued.
            self.active_game.write_game_state()
            self.prompt = f'\033[97m({self.active_game.playlist_name}'+self.auto_cmd+self.end_highlight
            print(f'A new game has been made with {num_cards} cards.')
            print('\nYou can use the "view" command to display and print the Mingo cards for this game.')
            print('You can begin playing tracks in random order by using the "nexttrack" command for each track.')
        except Exception as error:
            print(error)

    def do_continuegame(self, _):
        """If you stopped playing a game and exited this program, its state is \
saved. Use this command to resume playing a stopped game from when you stopped it.
        """

        try:
            self.active_game = restore_game_state()
            self.prompt = f'\033[97m({self.active_game.playlist_name}'+self.auto_cmd+self.end_highlight
            print('The previous game state has been restored. You can continue playing it now.')

        except Exception as error:
            print(error)    

    def do_view(self, card_num=None):
        """Specify a card number to view a single Mingo card from the active Mingo game. \
If no number is specified, all cards are displayed."""
        print("viewing card: ", card_num)
        if self.active_game:
            self.active_game.view_in_browser(card_num)
        else:
            print('There is not an active game. Create one using "makegame" and try again.')  

    def do_getinfo(self, _):
        """Display info about the currently active game."""
        if self.active_game:
            print(f'The currently active game has {self.active_game.n_cards} cards.')
        else:
           print('There is not an active game. Create one using "'"makegame"'" and try again.')  

    def do_nexttrack(self, _):
        """Play a randomly selected track from the active Mingo game."""
        if self.active_game:
            self.active_game.play_next_track()
            self.active_game.write_game_state()
            clear_web_votes(self)
            self.active_game.post_selections_to_web()

        else:
           print('There is not an active game. Create one using "'"makegame"'" and try again.')  


    def do_backup(self):

        if self.active_game:
            self.active_game.play_previous_track()
        else:
            print('There is not an active game.')
    

    def do_pause(self, _):
        """Pause the song that is currently playing. Use resume to resume playing."""
        if self.active_game:
            # print ("before pause currently playing: ", self.active_game.currently_playing())
            # Never pause when already paused! A player exception results!
            if self.active_game.currently_playing()[1]:
                self.active_game.pause()
            # print ("after pause currently playing: ", self.active_game.currently_playing())
            resume_at = self.active_game.currently_playing()[0]
            self.active_game.write_game_state()
            print(f'Paused after {resume_at} msec')
        else:
           print('There is not an active game. Create one using "'"makegame"'" and try again.')  
    
    def do_resume(self,_):
        """If a song has been paused, this command resumes playing the song."""
        if self.active_game:
            self.active_game.resume()
        else:
               print('There is not an active game. Create one using "'"makegame"'" and try again.')  

    def do_musicplayers(self, _):
        """List the music players that Spotify can use to play tracks. The first such player
        that is marked 'Active' in Spotify is selected to play your songs."""
        if self.player:
            self.player.show_available_players()
        else:
            print('No players can be listed.')

    def do_currentlyplaying(self, _):
        """Shows the progress info for the currently playing track."""
        if self.active_game:
            progress = self.active_game.currently_playing()[0]
            print(f'The track has been playing for {progress} msec')
        else:
           print('There is not an active game. Create one using "'"makegame"'" and try again.')  

    def do_history(self, replay_number):
        """ Show the tracks played so far and tell how many tracks remain to be played. 
        You can enter a track number to replay a track."""
        if self.active_game:
            self.active_game.game_monitor.show_played_tracks(self.active_game, replay_number, self)
        else:
           print('There is not an active game. Create one using "'"makegame"'" and try again.')  

    def do_testmode(self, autoplay_count):
        if self.active_game:
            if not autoplay_count:
                autoplay_count = '1'
            for idx in range(0,int(autoplay_count)):
                self.active_game.play_next_track(True)
            self.active_game.write_game_state()
            self.active_game.post_selections_to_web()
        else:
           print('There is not an active game. Create one using "'"makegame"'" and try again.')  


    
    def do_quit(self, args):
        """ 
        Quit the game, stopping the music player if it's playing and
        cleaning up as necessary. The state of a game in progress is saved
        so you can use continuegame to resume a game if you want.
        """
        self.do_auto('-2')
        cleanup_before_exiting(self)
        raise ExitCmdException()

    def do_save(self, save_number):
        """
        Save a game. You must supply a file name suffix (an integer is nice but
        not required) that will be used when loading this game.
        """
        if not save_number:
            print('Error: You must supply an argument with the save number to use')
        else:
            self.active_game.save_game_state(save_number)

    def do_load(self, load_number):
        """
        Load a previously saved game. You must supply a file name suffix (an integer is nice but
        not required) that was used when a game was saved.
        """
        if not load_number:
            print('Error: You must supply an argument with the load number for the game to load')
        else:
            try:
                self.active_game = load_game_state(load_number)
                self.prompt = f'\033[97m({self.active_game.playlist_name}'+self.auto_cmd+self.end_highlight
                print('A saved game state has been restored. You can continue playing it now.')

            except Exception as error:
                print(error)


#-----------------------------------------
# Global function definitions follow below
#-----------------------------------------
def empty_card_json(card_nbr):
    song_titles = []
    for _ in range(25):
        song_titles.append("-")
    
    # Create a dictionary to structure the data
    print("===================================")
    print("unloading card number: ", card_nbr)
    data = {"card_nbr": card_nbr, "songs": [{"id": i + 1, "title": title} for i, title in enumerate(song_titles)]}
    ret_json = json.dumps(data)
    print("===================================")
    
    # Convert the dictionary to a JSON string
    return ret_json # , indent=4)


def display_player_exception(e):
    exception_name = e.__class__.__name__
    if exception_name == 'SpotifyException':
        print(f'\n{exception_name}: \nMake sure the device you intend to play the track on is available and try again.')
    else:
        display_general_exception(e)

def display_general_exception(e):
    exception_name = e.__class__.__name__
    if exception_name == 'ReadTimeout' or exception_name == 'ConnectionError':
        print(f'\n{exception_name}:\nAn error occurred that indicates that you are not connected to the internet.')
    else:
        print(f'\n{exception_name}:\nAn unexpected error occurred.')

def cleanup_before_exiting(command_processor):
    if command_processor.active_game and command_processor.active_game.currently_playing()[1]:
        command_processor.active_game.pause()
    if command_processor.web_monitor:
        command_processor.web_monitor.stop()

def restore_game_state():
    print(f'\nRestoring from file {game_state_pathname}')
    path = Path(game_state_pathname)
    with open (path, 'rb') as fp:
        restored_game = pickle.load(fp)
    return restored_game

def load_game_state(load_number):
    saved_game_pathname = './.saved_game_'+load_number+'.bin'
    print(f'\nRestoring from file {saved_game_pathname}')
    path = Path(saved_game_pathname)
    with open (path, 'rb') as fp:
        restored_game = pickle.load(fp)
    return restored_game

def clear_web_votes(cmd_processor):
    if cmd_processor.web_monitor and cmd_processor.web_monitor._running:
        # We are monitoring user votes to skip but we have told the game to
        # start a new track.
        # Reset the number of votes to skip to zero because a new song is playing.
        requests.get(web_controller_url+'/clear')




#-----------------------------------------
# The main processing is declared below
#-----------------------------------------
if __name__ == '__main__':
    continue_running = True
    cp = None
    while continue_running:
        # Enter the command loop, handling Exceptions that break it. Some Exceptions
        # can be handled, like losing the network. We give the user a chance
        # to correct such errors. If the user believes an Exception
        # has been corrected, the command loop will restart.
        try:
            if cp is None:
                cp = CommandProcessor()
                cp.do_auto('-1')
            cp.cmdloop()
        except KeyboardInterrupt:
            print('Interrupted by ctrl-C, attempting to clean up first')
            try:
                cleanup_before_exiting(cp)
                sys.exit(0)
            except SystemExit:
                os._exit(0)
        except Exception as e:
            exception_name = e.__class__.__name__
    
            if exception_name == 'ExitCmdException':
                continue_running = False
                print('\nExiting the program...')
                continue
            else:
                display_general_exception(e)
            
            choice = input('Try correcting this problem and press "Y" to try again, or any other key to exit. ')
            if choice.upper() != 'Y':
                continue_running = False
                print('Exiting the program')