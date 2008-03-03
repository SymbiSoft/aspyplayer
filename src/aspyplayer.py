# Author: Douglas Fernando da Silva - doug.fernando at gmail.com
# Copyright 2008
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#     http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from random import shuffle
from key_codes import EKeyLeftArrow, EKeyRightArrow, EKeyUpArrow, EKeyDownArrow, EKeySelect 

import appuifw
import audio
import e32
import e32db
import md5
import os
import time
import urllib
import socket
import sys
import graphics

##########################################################
######################### MODELS 

class Music(object):
	def __init__(self, file_path=""):
		self.file_path = file_path;
		self.init_music()
		self.player = MusicPlayer(self)
		self.length = 0
		self.number = ""
		self.music_brainz_ID = ""
		self.played_at = 0
		self.position = 0
		self.now_playing_sent = False
	
	def init_music(self):
		if self.file_path:
			path = self.file_path
			fp = open(path, "r")
			fp.seek(-128, 2)
			fp.read(3)
	
			self.title = self.remove_X00(fp.read(30))
			if not self.title: 
				if len(self.file_path) > 18:
					self.title = "..." + self.file_path[-18:]
				else:
					self.title = self.file_path
			
			self.artist = self.remove_X00(fp.read(30))
			if not self.artist: self.artist = "Unknow"
			self.album = self.remove_X00(fp.read(30))
			if not self.album: self.album = "Unknow"
			self.year = self.remove_X00(fp.read(4))
			self.comment = self.remove_X00(fp.read(28))
	
			fp.close()
		else:
			self.title = None
			self.artist = None
			self.album = None
			self.year = None
			self.comment = None
	
	def remove_X00(self, value):
		return value.replace("\x00", "")
	
	def __str__(self):
		return u"  Artist: %s\n  Title: %s\n  Album: %s\n  Path: %s" % (
						self.artist, self.title, self.album, self.file_path)

	def play(self, callback):
		self.player.play(callback)
	
	def stop(self):
		self.player.stop()
		
	def pause(self):	
		self.player.pause()
		
	def volume_up(self):
		self.player.volume_up()

	def volume_down(self):
		self.player.volume_down()

	def is_playing(self):
		return self.player.is_playing()

	def get_player_position_in_seconds(self):
		return int(self.player.current_position() / 1e6)

	def can_update_position(self):
		curr_pos = self.get_player_position_in_seconds()
		if self.position != curr_pos:
			self.position = curr_pos
			return True
	
		return False

	def can_be_added_to_history(self):
		if self.length == 0: return False

		player_curr_pos = self.get_player_position_in_seconds()
		min_length_cond = player_curr_pos > 30
		min_length_played_cond = (player_curr_pos > 240 or (
				float(player_curr_pos) / self.length) > 0.5)
		
		return min_length_cond and min_length_played_cond

	def current_position_formatted(self):
		return self.format_secs_to_str(self.position)
	
	def length_formatted(self):
		return self.format_secs_to_str(self.length)
	
	def format_secs_to_str(self, input_seconds):
		hours = input_seconds / 3600
		seconds_remaining = input_seconds % 3600
		minutes = seconds_remaining / 60
		seconds = input_seconds % 60

		if hours >= 1:
			return unicode("%02i:%02i:%02i" % (hours, minutes, seconds))
		else:
			return unicode("%02i:%02i" % (minutes, seconds))
	
	def get_status_formatted(self):
		if self.is_playing():
			return "Playing"
		
		return "Stopped" 


class MusicPlayer(object):
	current_volume = -1

	def __init__(self, music, player=None):
		self.__music = music
		self.__paused = False
		self.loaded = False
		self.__player = player
		self.__current_position = None
		self.volume_step = 1
	
	def play(self, callback=None):
		if not self.__paused:
			self.__player = audio.Sound.open(self.__music.file_path)
			self.configure_volume()
			self.__music.length = int(self.__player.duration() / 1e6)
			self.__music.played_at = int(time.time())
			self.loaded = True
		else:
			self.__player.set_position(self.__current_position)
		
		self.__player.play(times=1, interval=0, callback=callback)

	def configure_volume(self):
		# HACK: I don't know why, but using directly the class attribute does not work
		volume = self.__class__.current_volume 
		if volume < 0: # default value = -1
			default_volume = self.__player.max_volume() / 4
			self.__class__.current_volume = default_volume

		self.volume_step = self.__player.max_volume() / 10
		self.__player.set_volume(self.__class__.current_volume)
		
	def stop(self):
		if self.loaded:
			self.__player.stop()
			self.__player.close()
			self.loaded = False
	
	def pause(self):
		if self.loaded:
			self.__current_position = player.current_position()
			self.__player.stop()
			self.__paused = True

	def volume_up(self):
		if self.loaded:
			self.__class__.current_volume = self.__class__.current_volume + self.volume_step
			if self.__class__.current_volume > self.__player.max_volume(): 
				self.__class__.current_volume = self.__player.max_volume()
			
			self.__player.set_volume(self.__class__.current_volume)
	
	def volume_down(self):
		if self.loaded:
			self.__class__.current_volume = self.__class__.current_volume - self.volume_step
			if self.__class__.current_volume < 0:
				self.__class__.current_volume = 0
			
			self.__player.set_volume(self.__class__.current_volume)

	def is_playing(self):
		if not self.__player: 
			return False
		
		return self.__player.state() == audio.EPlaying

	def current_volume_percentage(self):
		return int((float(self.__class__.current_volume) / self.__player.max_volume()) * 100)
	
	def current_position(self):
		return self.__player.current_position()


class MusicList(object):
	def __init__(self, musics, listener, random=False):
		self.__timer = e32.Ao_timer()
		self.__listener = listener
		self.__should_stop = False
		self.__current_index = 0
		self.__musics = musics
		self.is_playing = False

		if self.__musics:
			if random: 
				shuffle(self.__musics)
			
			self.current_music = self.__musics[0]
		else:
			self.current_music = None
	
	def is_empty(self):
		return len(self.__musics) < 1

	def __len__(self):
		return len(self.__musics)
	
	def play(self):
		self.__should_stop = False
		
		while self.current_music != None:
			self.current_music.play(self.play_callback)
			self.is_playing = True
			self.__listener.update_music(self.current_music)

			self.play_current_music()
				
			if self.__should_stop: break
			if not self.move_next(): break
			
			self.__timer.after(0.3) # time between the musics
	
		self.is_playing = False
	
	def set_current_index(self, index):
		self.__current_index = index
		self.current_music = self.__musics[self.__current_index]
	
	def play_current_music(self):
		added_to_history = False;
		while self.current_music.is_playing():
			if not added_to_history:
				if self.current_music.can_be_added_to_history():
					self.__listener.add_to_history(self.current_music)
					added_to_history = True
			
			if self.current_music.can_update_position():
				self.__listener.update_music(self.current_music)
			
			e32.ao_yield()

		self.__listener.finished_music(self.current_music)

	def play_callback(self, current, previous, err):
		pass
		
	def stop(self):
		self.__should_stop = True
		if self.current_music: 
			was_playing = self.current_music.is_playing()
			self.current_music.stop()
			if was_playing:
				self.__listener.finished_music(self.current_music)
			self.is_playing = False
			
	def next(self):
		self.stop()
		self.move_next()
		self.play()
		
	def previous(self):
		self.stop()
		self.move_previous()
		self.play()

	def move_next(self):
		last_index = len(self.__musics) - 1
		if self.__current_index < last_index:
			self.__current_index = self.__current_index + 1
			self.current_music = self.__musics[self.__current_index]
			return True
	
		return False
	
	def move_previous(self):
		if self.__current_index > 0:
			self.__current_index = self.__current_index - 1
			self.current_music = self.__musics[self.__current_index]
			return True
		
		return False

	def current_position_formated(self):
		return unicode("%i / %i" % (self.__current_index + 1, len(self.__musics)))


class MusicHistory(object):
	def __init__(self, repository, audio_scrobbler_service):
		self.__batch_size = 50
		self.__repository = repository
		self.__audio_scrobbler_service = audio_scrobbler_service

	def add_music(self, music):
		self.__repository.save_music(music)
	
	def clear(self):
		self.__repository.clear_history()
	
	def send_to_audioscrobbler(self):
		musics = self.__repository.load_all_history()
		if musics and len(musics) < self.__batch_size:
			if self.__audio_scrobbler_service.send(musics):
				self.clear()
				
		elif musics:
			self.send_batches_to_audioscrobbler(musics)

	def send_batches_to_audioscrobbler(self, musics):
		assert len(musics) >= self.__batch_size
		
		num_full_batches = len(musics) / self.__batch_size
		for i in range(num_full_batches):
			start = i * self.__batch_size
			end = start + self.__batch_size
			batch = musics[start:end]
			self.send_batch(batch)
		
		remainings = len(musics) % self.__batch_size
		if remainings > 0:
			batch = musics[len(musics)-remainings:len(musics)]
			self.send_batch(batch)
		
	def send_batch(self, musics_batch):
		if self.__audio_scrobbler_service.send(musics_batch):
			self.__repository.remove_musics(musics_batch)


class AudioScrobblerUser(object):
	def __init__(self, username, password, hashed=False):
		self.username = username
		if not hashed:
			self.password = md5.md5(password).hexdigest()
		else:
			self.password = password

##########################################################
######################### REPOSITORIES 

class MusicRepository(object):
	def __init__(self, db_helper):
		self.__db_helper = db_helper

	def distinct(self, collection):
		result = []
		for item in collection:
			if item not in result:
				result.append(item)
		
		return result
		
	def count_all(self):
		cmd = "SELECT Path FROM Music"
		rows = self.__db_helper.execute_reader(cmd)
		return len(rows)
	
	def count_all_artists(self):
		return len(self.find_all_artists())
	
	def count_all_albums(self):
		return len(self.find_all_albums())
	
	def find_all(self):
		cmd = "SELECT Path FROM Music"
		rows = self.__db_helper.execute_reader(cmd)
		result = [Music(row[0]) for row in rows]
		return self.distinct(result)
	
	def find_all_artists(self):
		cmd = "SELECT Artist FROM Music"
		rows = self.__db_helper.execute_reader(cmd)
		result = [row[0] for row in rows]
		return self.distinct(result)

	def find_all_albums(self):
		cmd = "SELECT Album FROM Music"
		rows = self.__db_helper.execute_reader(cmd)
		result = [row[0] for row in rows]
		return self.distinct(result)

	def find_all_by_artist(self, artist):
		cmd = "SELECT Path FROM Music WHERE Artist = '%s'" % artist.replace("'", "''")
		rows = self.__db_helper.execute_reader(cmd)
		result = [Music(row[0]) for row in rows]
		return result

	def find_all_by_album(self, album):
		cmd = "SELECT Path FROM Music WHERE Album = '%s'" % album.replace("'", "''")
		rows = self.__db_helper.execute_reader(cmd)
		result = [Music(row[0]) for row in rows]
		return result

	def save(self, music):
		cmd = "INSERT INTO Music (Path, Artist, Album) VALUES('%s', '%s', '%s')" % (music.file_path.replace("'", "''"),
								music.artist.replace("'", "''"), music.album.replace("'", "''"))
		result = self.__db_helper.execute_nonquery(cmd)
		assert result > 0

	def delete(self, music_path):
		cmd = "DELETE FROM Music WHERE Path = '%s'" % music_path
		result = self.__db_helper.execute_nonquery(cmd)
		assert result > 0

	def update_library(self, musics_path):
		all_music_in_db = self.find_all()
		all_music_in_db_path = [music.file_path for music in all_music_in_db]
		
		to_be_added = [x for x in musics_path if x not in all_music_in_db_path]
		to_be_deleted = [x for x in all_music_in_db_path if x not in musics_path]
		
		new_musics = []
		for file in to_be_added:
			try:
				music = Music(file)
				new_musics.append(music)
			except:
				pass
			
		for music in new_musics:
			self.save(music) 
	
		for music_path in to_be_deleted:
			self.delete(music_path)

		return (len(new_musics), len(to_be_deleted))


class AudioScrobblerUserRepository(object):
	def __init__(self, db_helper):
		self.__db_helper = db_helper

	def load(self):
		cmd = "SELECT UserName, Password FROM User"
		rows = self.__db_helper.execute_reader(cmd)
		if rows:
			return AudioScrobblerUser(rows[0][0], rows[0][1], True)
		
		return None
	
	def save(self, user):
		remove_cmd = "DELETE FROM User"
		insert_cmd = "INSERT INTO User (UserName, Password) VALUES('%s', '%s')" % (user.username.replace("'", "''"), user.password.replace("'", "''"))

		result = self.__db_helper.execute_nonquery(remove_cmd)
		result = self.__db_helper.execute_nonquery(insert_cmd)
		assert result > 0
	

class MusicHistoryRepository(object):
	def __init__(self, db_helper):
		self.__db_helper = db_helper
	
	def save_music(self, music):
		cmd = "INSERT INTO Music_History (Artist, Track, PlayedAt, Album, TrackLength) VALUES('%s', '%s', %i, '%s', %i)" % \
				(music.artist.replace("'", "''"), music.title.replace("'", "''"), 
					music.played_at, music.album.replace("'", "''"), music.length)
		
		result = self.__db_helper.execute_nonquery(cmd)
		assert result > 0

	def remove_musics(self, musics):
		for music in musics:
			cmd = "DELETE FROM Music_History WHERE PlayedAt = %i" % (music.played_at)
			self.__db_helper.execute_nonquery(cmd)
	
	def clear_history(self):
		cmd = "DELETE FROM Music_History"
		self.__db_helper.execute_nonquery(cmd)
	
	def load_all_history(self):
		cmd = "SELECT Artist, Track, PlayedAt, Album, TrackLength FROM Music_History"
		rows = self.__db_helper.execute_reader(cmd)
		result = []
		for row in rows:
			music = Music()
			music.artist = row[0]
			music.title = row[1]
			music.played_at = row[2]
			music.album = row[3]
			music.length = row[4]
			result.append(music)
	
		return result


##########################################################
######################### SERVICES 

class AudioScrobblerError(Exception):
	pass


class AudioScrobblerCredentialsError(Exception):
	pass


class NoAudioScrobblerUserError(Exception):
	pass


class AudioScrobblerService(object):
	def __init__(self, user_repository): 
		self.__logger = LogFactory.create_for(self.__class__.__name__)
		self.logged = False
		self.__user_repository = user_repository
		self.__handshake_url = "http://post.audioscrobbler.com/"
		self.__handshake_data = None
		self.__session_id = None
		self.__now_url = None
		self.__post_url = None
	
	def set_credentials(self, user):
		self.__user_repository.save(user)
		
	def create_handshake_data(self):
		user = self.__user_repository.load()
		if not user:
			raise NoAudioScrobblerUserError("You must set an user/password first")
		
		client_id = "tst"
		client_version = "1.0"
		tstamp = int(time.time())
		token  = md5.md5("%s%d" % (user.password, tstamp)).hexdigest()
   		
   		values = {
			"hs": "true", 
			"p": '1.2', 
			"c": client_id, 
			"v": client_version, 
			"u": user.username, 
			"t": tstamp, 
			"a": token
	 	}
   		
   		self.__handshake_data = urllib.urlencode(values)

	def login(self):
		try:
			self.create_handshake_data()
			response = urllib.urlopen("%s?%s" % (self.__handshake_url, self.__handshake_data))
			as_response_data = self.handle_handshake_response(response)
			self.__session_id, self.__now_url, self.__post_url = as_response_data
			self.__logger.debug("Login was OK: ID %s, NowUrl %s, PostUrl %s" % (as_response_data))
			self.logged = True
		except NoAudioScrobblerUserError: 
			self.logged = False
			raise
		except:
			self.__logger.debug("Login error: '%s'" % ''.join(traceback.format_exception(*sys.exc_info())))
			self.logged = False
			raise
		
	def handle_handshake_response(self, response):
		result = response.read()
		lines = result.split("\n")

		if lines[0] == "OK":
			return (lines[1], lines[2], lines[3])
		else:
			self.handle_handshake_error(lines[0])
		
	def handle_handshake_error(self, error):
		if error == "BADAUTH":
			raise AudioScrobblerCredentialsError("Bad username/password")
		elif error == "BANNED":
			raise AudioScrobblerError("'This client-version was banned by Audioscrobbler. Please contact the author of this module!'")
		elif error == "BADTIME":
			raise AudioScrobblerError("'Your system time is out of sync with Audioscrobbler. Consider using an NTP-client to keep you system time in sync.'")
		elif error.startswith("FAILED"):
	  		raise AudioScrobblerError("Authentication with AS failed. Reason: %s" % error)
		else:
			raise AudioScrobblerError("Authentication with AS failed.")
	
	def check_login(self):
		if not self.logged:
			raise AudioScrobblerError("You must be logged to execute this operation")
		
	def now_playing(self, music):
		if music.now_playing_sent: return True
		self.check_login()
		
		values = {
			"s": self.__session_id, 
			"a": unicode(music.artist).encode("utf-8"), 
			"t": unicode(music.title).encode("utf-8"), 
			"b": unicode(music.album).encode("utf-8"), 
			"l": music.length, 
			"n": music.number, 
			"m": music.music_brainz_ID
		}

		try:
			data = urllib.urlencode(values)
			response = urllib.urlopen(self.__now_url, data)
			result = response.read()

			if result.strip() == "OK":
				music.now_playing_sent = True
				return True
			elif result.strip() == "BADSESSION":
				raise AudioScrobblerError("Invalid session")
		except:
			self.__logger.debug("Now playing error: '%s'" % ''.join(traceback.format_exception(*sys.exc_info())))
		
		return False
	
	def send(self, musics):
		self.check_login()
		
		try:
			data = self.create_send_music_data(musics)
			response = urllib.urlopen(self.__post_url, data)
			result = response.read()
			result_value = result.split("\n")[0]
			
			if result_value == "OK":
				return True
			elif result_value.startswith("FAILED"):
				raise AudioScrobblerError("Submission to AS failed. Reason: %s" % result_value)
		except:
			self.__logger.debug("Scrobbling error: '%s'" % ''.join(traceback.format_exception(*sys.exc_info())))

		return False

	def create_send_music_data(self, musics):
		musics_data = []
		
		for music in musics:
			musics_data.append({ 
				"a": unicode(music.artist).encode("utf-8"), 
				"t": unicode(music.title).encode("utf-8"), 
				"i": music.played_at, 
				"o": "P", 
				"r": "", 
				"l": music.length, 
				"b": unicode(music.album).encode("utf-8"), 
				"n": music.number, 
				"m": music.music_brainz_ID
			})

		values = {}
		i = 0
		for item in musics_data:
			for key in item:
				values[key + ("[%d]" % i)] = item[key]
			i = i + 1
			
		values["s"] = self.__session_id
		data = urllib.urlencode(values)
		
		return data


##########################################################
######################### INFRASTRUCTURE 

class LogFactory(object):
	def create_for(name):
		logger = Logger(str(name), "c:\\data\\aspyplayer\\log.txt") 
		return logger
	
	create_for = staticmethod(create_for)


class Logger(object):
	def __init__(self, name, path):
		self.name = name
		self.path = path
		self.level = 0
		
	def debug(self, msg):
		if self.level == 0:
			f = open(self.path, "a")
			f.write("DEBUG - %s" % msg)
			f.close()
	
	def info(self, msg):
		if self.level > 0:
			f = open(self.path, "a")
			f.write("DEBUG - %s" % msg)
			f.close()
			

class ServiceLocator(object):
	def __init__(self):
		self.file_system_services = FileSystemServices()
		self.db_helper = DbHelper("c:\\data\\aspyplayer\\aspyplayer.db", self.file_system_services)
		self.history_repository = MusicHistoryRepository(self.db_helper)
		self.user_repository = AudioScrobblerUserRepository(self.db_helper)
		self.as_service = AudioScrobblerService(self.user_repository)	
		self.music_history = MusicHistory(self.history_repository, self.as_service)
		self.music_repository = MusicRepository(self.db_helper)

	def close(self):
		self.file_system_services = None
		self.db_helper.close()
		self.db_helper = None
		self.history_repository = None
		self.user_repository = None
		self.as_service = None	
		self.music_history = None
		self.music_factory = None

class FileSystemServices:
	def find_all_files(self, root_dir, file_extension):
		result = []
		predicate = lambda f: f.endswith(file_extension)
		
		def walk(arg, dirname, names):
			files_filtered = filter(predicate, names)
			
			for file in files_filtered:
				full_file_path = "%s\\%s" %(dirname, file.decode('utf-8'))
				result.append(full_file_path)
		
		os.path.walk(root_dir, walk, None)
		
		return result

	def exists(self, path):
		return os.path.exists(path)

	def create_base_directories_for(self, full_path):
		dir = os.path.split(full_path)[0]
		if not os.path.exists(dir):
			os.makedirs(dir)

	def get_all_music_files_path_in_device(self):
		all_musics_in_c = self.find_all_files("C:\\", ".mp3")
		all_musics_in_e = self.find_all_files("E:\\", ".mp3")
		all_music = []
		all_music.extend(all_musics_in_c)
		all_music.extend(all_musics_in_e)
		return all_music

class DbHelper(object):
	def __init__(self, dbpath, file_system_services):
		self.__db_path = dbpath
		self.__fs_services = file_system_services
		db_already_exists = self.__fs_services.exists(self.__db_path) 
		
		self.db = e32db.Dbms()
		self.dbv = e32db.Db_view()
		
		if db_already_exists:
			self.db.open(unicode(dbpath))
		else:
			self.check_db_directory()
			self.db.create(unicode(dbpath))
			self.db.open(unicode(dbpath))
			self.create_tables()

	def close(self):
		self.db.close()

	def check_db_directory(self):
		self.__fs_services.create_base_directories_for(self.__db_path)

	def execute_nonquery(self, sql):
		return self.db.execute(unicode(sql))

	def execute_reader(self, sql):
		self.dbv.prepare(self.db, unicode(sql))
		self.dbv.first_line()
		result = []
		
		for i in range(self.dbv.count_line()):
			self.dbv.get_line()
			row = []
			
			for i in range(self.dbv.col_count()):
				try:
					row.append(self.dbv.col(i+1))
				except:    # in case coltype 16
					row.append(None)
			
			result.append(row)
			self.dbv.next_line()
		
		return result

	def create_tables(self):
		self.create_music_history_table()
		self.create_user_table()
		self.create_music_table()
	
	def create_music_table(self):
		cmd = "CREATE TABLE Music (Path varchar(200), Artist varchar(200), Album varchar(200))"
		self.execute_nonquery(cmd)
		# TODO: add index
	
	def create_music_history_table(self):
		cmd = "CREATE TABLE Music_History (Artist varchar(200), Track varchar(200), PlayedAt integer, Album varchar(200), TrackLength integer)"
		self.execute_nonquery(cmd)

	def create_user_table(self):
		cmd = "CREATE TABLE User (UserName varchar(200), Password varchar(200))"
		self.execute_nonquery(cmd)


##########################################################
######################### USER INTERFACE 

class PlayerUI(object):
	def __init__(self, service_locator):
		self.navigator = ScreenNavigator(self, service_locator)
		self.__applock = e32.Ao_lock()
		
	def quit(self):
		try:
			self.navigator.close()
		finally:
			self.__applock.signal()
	
	def close(self):
		appuifw.app.menu = []
		appuifw.app.body = None
		appuifw.app.exit_key_handler = None

	def start(self):
		self.navigator.go_to_main_window()
		self.__applock.wait()


class ScreenNavigator(object):
	def __init__(self, player_ui, service_locator):
		self.__player_ui = player_ui
		self.__service_locator = service_locator
		self.__as_presenter = AudioScrobblerPresenter(self.__service_locator)
		
		# Application screens
		self.__main_window = MainWindow(self.__player_ui, self, self.__service_locator)
		self.__select_window = SelectWindow(self.__player_ui, self, self.__service_locator)
		self.__all_musics_window = AllMusicsWindow(self.__player_ui, self, self.__service_locator)
		self.__artists_window = ArtistsWindow(self.__player_ui, self, self.__service_locator)
		self.__albums_window = AlbumsWindow(self.__player_ui, self, self.__service_locator)
		self.__musics_window = MusicsWindow(self.__player_ui, self)
		self.__now_playing_window = None
	
	def go_to_main_window(self):
		self.go_to(self.__main_window)

	def go_to_select_window(self):
		self.go_to(self.__select_window)

	def go_to_all_musics_window(self):
		self.go_to(self.__all_musics_window)

	def go_to_artists_window(self):
		self.go_to(self.__artists_window)

	def go_to_albums_window(self):
		self.go_to(self.__albums_window)

	def go_to_musics(self, musics):
		self.__musics_window.musics = musics
		self.go_to(self.__musics_window)

	def go_to_now_playing(self, musics=[], index=0):
		if not self.__now_playing_window:
			self.__now_playing_window = NowPlayingWindow(self.__player_ui, self)
		elif not musics:
			if self.__now_playing_window.can_be_shown():
				self.go_to(self.__now_playing_window)
			else:
				self.__now_playing_window.show_message("No music selected yet")

		if musics:
			music_list = MusicList(musics, self.__now_playing_window)
			self.__now_playing_window.update_music_list(music_list)
			self.__now_playing_window.music_list.set_current_index(index)
			self.go_to(self.__now_playing_window)

	def go_to(self, window):
		if self.__now_playing_window:
			self.__now_playing_window.is_visible = (window == self.__now_playing_window)
		
		self.__as_presenter.set_view(window)
		window.as_presenter = self.__as_presenter
		
		appuifw.app.body = window.body
		appuifw.app.menu = window.menu
		appuifw.app.title = window.title

		window.show()

	def close(self):
		if self.__now_playing_window:
			self.__now_playing_window.close()


class Window(object):
	def __init__(self, player_ui, navigator, title="Audioscrobbler PyS60 Player"):
		self.player_ui = player_ui
		self.navigator = navigator
		self.title = unicode(title)
		self.body = None
		self.menu = []
		self.as_presenter = None
		appuifw.app.screen = "normal"

	def about(self):
		self.show_message("asPyPlayer\nCreated by Douglas\n(doug.fernando at gmail)\n\ncode.google.com/p/aspyplayer")

	def show_message(self, message):
		appuifw.note(unicode(message), "info")

	def show_error_message(self, message):
		appuifw.note(unicode(message), "error")

	def ask_text(self, info):
		return appuifw.query(unicode(info), "text")

	def ask_password(self, info):
		return appuifw.query(unicode(info), "code")

	def ask(self, question):
		return appuifw.query(unicode(question), "query")

	def show(self):
		appuifw.app.exit_key_handler = self.player_ui.quit

	def tests(self):
		if self.ask("For development purposes only. It may crash the application. Continue?"):
			Fixtures().run()

	def basic_lastfm_menu_items(self):
			return [
			(u"Last.fm", (
				(u"Connect", self.as_presenter.connect), 
				(u"Clear History", self.as_presenter.clear_as_db), 
				(u"Submit History", self.as_presenter.send_history),
				(u"Set Credentials", self.as_presenter.create_as_credentials)))]

	def basic_last_menu_items(self):
		return [
			(u"Admin", (
				(u"Settings", lambda: None), 
				(u"Testing", self.tests))),
			(u"About", self.about), 
			(u"Exit", self.quit)]

	def update_menu(self, new_menu):
		if self.menu:
			while self.menu:
				self.menu.pop()
		
		self.menu.extend(new_menu)

	def quit(self):
		if self.ask("Are you sure you want to exit the application?"):
			self.player_ui.quit()

	
class MainWindow(Window):
	def __init__(self, player_ui, navigator, service_locator):
		Window.__init__(self, player_ui, navigator)
		self.__fs_services = service_locator.file_system_services
		self.__music_repository = service_locator.music_repository
		self.body = appuifw.Listbox(self.get_list_items(), self.go_to)
	
	def go_to(self):
		index = self.body.current()
		if index == 0:
			self.navigator.go_to_select_window()
		else:
			self.about()
	
	def get_list_items(self):
		items = [(u"Your Musics", unicode("%i musics" % self.__music_repository.count_all())), 
				(u"About", u"code.google.com/p/aspyplayer/")]
		
		return items
	
	def update_music_library(self):
		self.show_message("This operation can take some time...")
		result = self.__music_repository.update_library(self.get_all_music_files_path())
		self.body.set_list(self.get_list_items())
		self.show_message("Library updated. Added: %i, Deleted: %i" % result)
	
	def get_all_music_files_path(self):
		return self.__fs_services.get_all_music_files_path_in_device()
	
	def get_menu_items(self):
		items = [
			(u"Update Musics Library", self.update_music_library),
			(u"Now playing", self.navigator.go_to_now_playing)]
		items.extend(self.basic_lastfm_menu_items())
		items.extend(self.basic_last_menu_items())
		
		return items
	
	def show(self):
		self.update_menu(self.get_menu_items())
		appuifw.app.exit_key_handler = self.quit


class SelectWindow(Window):
	def __init__(self, player_ui, navigator, service_locator):
		Window.__init__(self, player_ui, navigator)
		self.__music_repository = service_locator.music_repository
		self.body = appuifw.Listbox([(u"empty", u"empty")], self.go_to)
		self.menu = self.get_menu_items()

	def get_list_items(self):
		items = [(u"All Music", unicode("%i musics" % self.__music_repository.count_all())), 
				(u"Artists", u"%i artists" % self.__music_repository.count_all_artists()),
				(u"Albums", u"%i albums" % self.__music_repository.count_all_albums())]
		return items

	def back(self):
		self.navigator.go_to_main_window()
	
	def get_menu_items(self):
		items = [
			(u"Back", self.back),
			(u"Now playing", self.navigator.go_to_now_playing)]
		items.extend(self.basic_last_menu_items())

		return items

	def go_to(self):
		index = self.body.current()
		if index == 0:
			self.navigator.go_to_all_musics_window()
		elif index == 1:
			self.navigator.go_to_artists_window()
		else:
			self.navigator.go_to_albums_window()

	def show(self):
		self.body.set_list(self.get_list_items())
		appuifw.app.exit_key_handler = self.back


class MusicsWindow(Window):
	def __init__(self, player_ui, navigator, title=""):
		if title: 
			Window.__init__(self, player_ui, navigator, title)
		else:
			Window.__init__(self, player_ui, navigator)
		
		self.body = appuifw.Listbox([u"empty"], self.go_to)
		self.menu = self.get_menu_items()
		self.musics = []

	def get_list_items(self):
		list_items = []
		bad_musics = []
		i = 1
		for music in self.musics:
			try:
				title = unicode(music.title)
				list_items.append(u"%i-%s" % (i, title))
			except:
				bad_musics.append(music)
			i += 1
		
		return list_items
	
	def back(self):
		self.navigator.go_to_select_window()
	
	def get_menu_items(self):
		items = [
			(u"Back", self.back),
			(u"Now playing", self.navigator.go_to_now_playing)]
		items.extend(self.basic_last_menu_items())

		return items

	def go_to(self):
		index = self.body.current()
		self.navigator.go_to_now_playing(self.musics, index)

	def show(self):
		self.body.set_list(self.get_list_items())
		appuifw.app.exit_key_handler = self.back


class AllMusicsWindow(MusicsWindow):
	def __init__(self, player_ui, navigator, service_locator):
		MusicsWindow.__init__(self, player_ui, navigator)
		self.__music_repository = service_locator.music_repository
	
	def show(self):
		self.musics = self.__music_repository.find_all()
		MusicsWindow.show(self)


class ArtistsWindow(Window):
	def __init__(self, player_ui, navigator, service_locator):
		Window.__init__(self, player_ui, navigator)
		self.__music_repository = service_locator.music_repository
			
		self.body = appuifw.Listbox([u"empty"], self.go_to)
		self.menu = self.get_menu_items()

	def get_list_items(self):
		self.artists = map(unicode, self.__music_repository.find_all_artists())
		if not self.artists:
			self.artists.append(u"empty")
		
		self.artists.sort(lambda x, y: cmp(x.lower(), y.lower()))
		
		return self.artists

	def back(self):
		self.navigator.go_to_select_window()
	
	def get_menu_items(self):
		items = [
			(u"Back", self.back),
			(u"Now playing", self.navigator.go_to_now_playing)]
		items.extend(self.basic_last_menu_items())

		return items

	def go_to(self):
		index = self.body.current()
		artist_selected = self.artists[index]
		musics = self.__music_repository.find_all_by_artist(artist_selected)
		assert musics
		self.navigator.go_to_musics(musics)

	def show(self):
		self.body.set_list(self.get_list_items())
		appuifw.app.exit_key_handler = self.back


class AlbumsWindow(Window):
	def __init__(self, player_ui, navigator, service_locator):
		Window.__init__(self, player_ui, navigator)
		self.__music_repository = service_locator.music_repository
			
		self.body = appuifw.Listbox([u"empty"], self.go_to)
		self.menu = self.get_menu_items()

	def get_list_items(self):
		self.albums = map(unicode, self.__music_repository.find_all_albums())
		if not self.albums:
			self.albums.append(u"empty")
		
		self.albums.sort(lambda x, y: cmp(x.lower(), y.lower()))
		
		return self.albums
	
	def back(self):
		self.navigator.go_to_select_window()
	
	def get_menu_items(self):
		items = [
			(u"Back", self.back),
			(u"Now playing", self.navigator.go_to_now_playing)]
		items.extend(self.basic_last_menu_items())

		return items

	def go_to(self):
		index = self.body.current()
		album_selected = self.albums[index]
		musics = self.__music_repository.find_all_by_album(album_selected)
		assert musics
		self.navigator.go_to_musics(musics)

	def show(self):
		self.body.set_list(self.get_list_items())
		appuifw.app.exit_key_handler = self.back


class NowPlayingWindow(Window):
	def __init__(self, player_ui, navigator):
		Window.__init__(self, player_ui, navigator)
		self.music_list = None
		self.is_visible = False
		self.bg_img = self.load_image()
		self.body = appuifw.Canvas(self.render) # TODO: destruir quando nao estiver visivel
		self.presenter = None

	def load_image(self):
		possible_locations = ["E:\\python\\now_playing_bg.jpg", "C:\\python\\now_playing_bg.jpg"]
		possible_locations.append(os.path.join(sys.path[0], "now_playing_bg.jpg"))
		
		for location in possible_locations:
			if os.path.exists(location):
				try:
					return graphics.Image.open(location)
				except:
					pass

	def can_be_shown(self):
		return self.music_list

	def close(self):
		self.stop()

	def render(self, coord=(100,100)):
		if self.is_visible and self.music_list:
			if self.music_list.current_music:
				self.show_music_information(self.music_list.current_music)

	def stop(self):
		if self.music_list:
			if self.music_list.is_playing: 
				self.music_list.stop()

	def update_music_list(self, music_list):
		self.stop()
		self.music_list = music_list
		self.presenter = NowPlayingPresenter(self, music_list)

	def show_music_information(self, music):
		if not self.is_visible: return

		self.body.clear()
		self.body.blit(self.bg_img)
		
		tr = TextRenderer(self.body)
		tr.spacing = 6
		tr.set_position((10,10))
		
		tr.render_line("Currently...", (u"normal", 18, graphics.FONT_BOLD), fill=(255, 0, 0))
		tr.add_blank_line()
		tr.render_line("  Artist: %s" % music.artist, (u"title", 16, graphics.FONT_BOLD))
		tr.render_line("  Track: %s" % music.title, (u"title", 16, graphics.FONT_BOLD))
		tr.add_blank_line()
		tr.render_line("     %s - %s" % (music.current_position_formatted(), 
					music.length_formatted()), (u"normal", 13, graphics.FONT_BOLD))
		tr.render_line("     Status: %s       %s" % (music.get_status_formatted(), 
					self.music_list.current_position_formated()), (u"normal", 13, graphics.FONT_BOLD))
		tr.add_blank_line()
		
	def finished_music(self, music):
		self.as_presenter.finished_music(music)
		
	def update_music(self, music):
		if self.is_visible:
			self.show_music_information(music)
			self.as_presenter.audio_scrobbler_now_playing(music)
	
	def add_to_history(self, music):
		self.as_presenter.add_to_history(music)

	def back(self):
		self.navigator.go_to_select_window()

	def get_menu_items(self):
		items = [
			(u"Back", self.back),
			(u"Controls", (
				(u"Play", self.presenter.play),
				(u"Stop", self.presenter.stop), 
				(u"Next", self.presenter.next),
				(u"Previous", self.presenter.previous))), 
			(u"Volume", (
				(u"Up", self.presenter.volume_up), 
				(u"Down", self.presenter.volume_down)))]
		items.extend(self.basic_lastfm_menu_items())
		items.extend(self.basic_last_menu_items())
		return items

	def bind_key_events(self):
		self.body.bind(EKeyRightArrow, self.presenter.next)
		self.body.bind(EKeyLeftArrow, self.presenter.previous)
		self.body.bind(EKeyUpArrow, self.presenter.volume_up)
		self.body.bind(EKeyDownArrow, self.presenter.volume_down)
		self.body.bind(EKeySelect, self.presenter.play_stop)
	
	def show(self):
		appuifw.app.exit_key_handler = self.back
		self.update_menu(self.get_menu_items())
		self.bind_key_events()
		
		if not self.music_list.is_playing:
			self.presenter.play()

		self.show_music_information(self.music_list.current_music)

		

class NowPlayingPresenter(object):
	def __init__(self, view, music_list):
		self.view = view
		self.music_list = music_list

	def is_in_play_mode(self):
		return self.music_list
	
	def play(self): 
		if not self.music_list.is_empty():
			self.music_list.play()

	def play_stop(self):
		if self.music_list:
			if self.music_list.current_music.is_playing():
				self.stop()
			else:
				self.play()

	def pause(self): 
		if self.music_list:
			self.music_list.play()
	
	def stop(self):
		if self.music_list:	
			self.music_list.stop()
			self.view.update_music(self.music_list.current_music)
			
	def next(self):
		if self.music_list:	
			self.music_list.next()

	def previous(self):
		if self.music_list:	
			self.music_list.previous()

	def volume_up(self):
		if self.music_list:	
			self.music_list.current_music.volume_up()
			self.show_current_volume()

	def show_current_volume(self):
		self.view.show_message("Current volume: %s%%" % (
						self.music_list.current_music.player.current_volume_percentage()))
		
	def volume_down(self):
		if self.music_list:	
			self.music_list.current_music.volume_down()
			self.show_current_volume()
		

class AudioScrobblerPresenter(object):
	def __init__(self, service_locator):
		self.view = None
		self.__ap_services = None
		self.__music_history = service_locator.music_history
		self.__audio_scrobbler_service = service_locator.as_service
		self.__now_playing_error_counter = 0

	def set_view(self, view):
		self.view = view
		self.__ap_services = AccessPointServices(self.view)

	def clear_as_db(self):
		if self.view.ask("Are you sure you want to clear your history?"):
			self.__music_history.clear()
	
	def disconnect(self):
		if self.is_online():
			self.__ap_services.disconnect()
	
	def connect(self):
		if not self.is_online():
			self.__ap_services.set_accesspoint()
			try:
				return self.try_login()
			except NoAudioScrobblerUserError:
				self.create_as_credentials()
				return self.try_login()
			
			return False
		else:
			self.view.show_message("Already connected!")
			return False
	
	def try_login(self):
		try:
			self.__audio_scrobbler_service.login()
			return True
		except AudioScrobblerCredentialsError:
			self.view.show_error_message("Bad Username/Password. Change your credentials")
		except NoAudioScrobblerUserError: raise
		except:
			self.view.show_error_message("It was not possible to log in.")

		return False
	
	def create_as_credentials(self):
		user_name = self.view.ask_text("Inform your username")
		if not user_name: return
		
		password = self.view.ask_password("Inform your password")
		if not password: return
		
		self.__audio_scrobbler_service.set_credentials(AudioScrobblerUser(user_name, password))
		self.view.show_message("Credentials saved")
		
	def send_history(self):
		if not self.is_online():
			if not self.connect():
				self.show_cannot_connect()

		self.__music_history.send_to_audioscrobbler()
	
	def show_cannot_connect(self):
		self.view.show_error_message("It was not possible to connect!")
	
	def play(self): 
		if self.check_selected_directory():
			self.music_list.play()

	def finished_music(self, music):
		if self.is_online():
			self.__music_history.send_to_audioscrobbler()
	
	def add_to_history(self, music):
		self.__music_history.add_music(music)
	
	def is_online(self):
		return self.__audio_scrobbler_service.logged
	
	def audio_scrobbler_now_playing(self, music):
		if self.is_online():
			if not self.__audio_scrobbler_service.now_playing(music):
				self.__now_playing_error_counter += 1
				if self.__now_playing_error_counter % 5 == 0:
					self.view.show_message("It was not possible to send now playing to Last.fm")


class TextRenderer:
	def __init__(self, canvas):
		self.canvas = canvas
		self.coords = [0,0]
		self.spacing = 1

	def set_position(self, coords):
		self.coords = coords

	def add_blank_line(self, line_height=10):
		self.coords[1] += line_height

	def move_cursor(self, x, y):
		self.coords[0] += x
		self.coords[1] += y

	def render_line(self, text, font=(u"normal", 16), fill=0x000000):
		bounding, to_right, fits = self.canvas.measure_text(text, font=font)

		self.canvas.text([self.coords[0], self.coords[1] - bounding[1]], 
										unicode(text), font=font, fill=fill)

		self.coords = [self.coords[0],
					self.coords[1] - bounding[1] + bounding[3] + self.spacing]


class AccessPointServices(object):
	def __init__(self, view, access_point_file_path="e:\\apid.txt"):
		self.__view = view
		self.__ap_file_path = access_point_file_path
	
	def unset_accesspoint(self):
		f = open(self.__ap_file_path, "w")
		f.write(repr(None))
		f.close()
		self.__view.show_message("Default access point is unset ")

	def select_accesspoint(self):
		apid = socket.select_access_point()
		if self.__view.ask("Set as default?") == True:
			f = open(self.__ap_file_path, "w")
			f.write(repr(apid))
			f.close()
			self.__view.show_message("Saved default access point")
		
		try:
			apo = socket.access_point(apid)
			socket.set_default_access_point(apo)
		except:
			self.__view.show_error_message("It was not possible to set a connection")

	def disconnect(self):
		socket.socket.close()

	def set_accesspoint(self):
		try:
			f = open(self.__ap_file_path, "rb")
			setting = f.read()
			apid = eval(setting)
			f.close()
			if apid:
				apo = socket.access_point(apid)
				socket.set_default_access_point(apo)
			else:
				self.select_accesspoint()
		except:
			self.select_accesspoint()


class AspyPlayerApplication(object):
	def run(self):
		sl = ServiceLocator()
		ui = PlayerUI(sl)
	
		try:
			ui.start()
		finally:
			ui.close()
			sl.close()
			print "bye"

##########################################################
######################### TESTING 

class Fixture(object):
	def assertEquals(self, expected, result, description):
		if expected != result:
			print "expected: %s - found: %s for -> %s" % (expected, result, description)
		assert expected == result
	
	def assertTrue(self, condition, description):
		if not condition: print description + " => NOT OK"
		assert condition

	def load_music(self):
		music = Music("E:\\Music\\Bloc Party - Silent Alarm\\01 - Like Eating Glass.mp3")
		music.length = 261
		music.played_at = int(time.time()) - 40
		return music
	
class AudioScrobblerServiceFixture(Fixture):
	def __init__(self):
		self.sl = ServiceLocator()
		f = open("E:\\as.pwd", "rb")
		self.pwd = f.read().replace(" ", "")
		f.close()
		self.title = "Audio scrobbler service tests"

	def run(self):
		if self.pwd:
			as_service = self.sl.as_service
			as_service.set_credentials(AudioScrobblerUser("doug_fernando", self.pwd))
			as_service.login()
		
			self.assertTrue(as_service.logged, "Logging")
			
			music = self.load_music()
			result = as_service.now_playing(music)
			self.assertTrue(result, "Sent now playing to AS")
			
			result = as_service.send([music])
			self.assertTrue(result, "Sent music to AS")


class FileSystemServicesFixture(Fixture):
	def __init__(self):
		self.title = "File System Services tests"

	def run(self):
		t = os.listdir("E:\\Music\\Bloc Party - Silent Alarm\\")
		
		fss = FileSystemServices()
		files = fss.find_all_files("E:\\Music\\Bloc Party - Silent Alarm\\", ".mp3")
		self.assertEquals(16, len(files), "Num of files loaded")
		
		files = fss.find_all_files("E:\\Music\\Muse - Absolution", ".mp3")
		self.assertEquals(14, len(files), "Num of files loaded")


class MusicHistoryRepositoryFixture(Fixture):		
	def __init__(self):
		self.sl = ServiceLocator()
		self.title = "Music history repository tests"

	def run(self):
		repos = self.sl.history_repository
		repos.clear_history()

		musics = repos.load_all_history()
		self.assertTrue(len(musics) == 0, "Repository empty")

		music = self.load_music()
		repos.save_music(music)
		musics = repos.load_all_history()
		self.assertTrue(len(musics) > 0, "Repository not empty")


class MusicFixture(Fixture):
	def __init__(self):
		self.sl = ServiceLocator()
		self.title = "Music tests"

	def run(self):
		music = self.load_music()
		music.position = 135
		
		self.assertTrue(unicode(music.title) == u"Like Eating Glass", "Music title")
		self.assertTrue(unicode(music.artist) == u"Bloc Party", "Music artist")
		self.assertTrue(unicode(music.album) == u"Silent Alarm [Japan Bonus Trac", "Music Album")
		
		length_formatted = music.length_formatted()
		self.assertTrue(unicode("04:21") == unicode(length_formatted), "Correct length formatted") 
		
		current_pos_formatted = music.current_position_formatted()
		self.assertTrue(unicode("02:15") == unicode(current_pos_formatted), "Current position formatted")
		
		self.assertTrue(music.remove_X00("ABC\x00") == "ABC", "Remove unicode spaces")
		
		music.get_player_position_in_seconds = lambda: 200
		self.assertTrue(music.can_update_position(), "Can update position")
		self.assertTrue(music.can_update_position() == False, "Cannot update position")

		music.get_player_position_in_seconds = lambda: 20
		self.assertTrue(music.can_be_added_to_history() == False, "Cannot add to history")
		music.length = 600
		music.get_player_position_in_seconds = lambda: 200
		self.assertTrue(music.can_be_added_to_history() == False, "Cannot add to history")
		music.get_player_position_in_seconds = lambda: 250
		self.assertTrue(music.can_be_added_to_history(), "Can add to history")
		music.length = 261
		music.get_player_position_in_seconds = lambda: 135
		self.assertTrue(music.can_be_added_to_history(), "Can add to history")

		music.is_playing = lambda: True
		self.assertEquals("Playing", music.get_status_formatted(), "playing status formatted")

		music.is_playing = lambda: False
		self.assertEquals("Stopped", music.get_status_formatted(), "stopped status formatted")


class UserFixture(Fixture):
	def __init__(self):
		self.sl = ServiceLocator()
		self.title = "User tests"

	def run(self):
		user = AudioScrobblerUser("doug_fernando", "hiaa29348")
		self.assertTrue(user.username == "doug_fernando", "Username")
		self.assertTrue(user.password == "894f117cc2e31a7195ad628cadf8da1a", "Password hashed")

		user2 = AudioScrobblerUser("doug_fernando", "abc", True)
		self.assertTrue(user2.username == "doug_fernando", "Username")
		self.assertTrue(user2.password == "abc", "Password")


class MusicPlayerFixture(Fixture):
	def __init__(self):
		self.sl = ServiceLocator()
		self.title = "Music player tests"

	def run(self):
		audio_player = FakePlayer()
		
		player = MusicPlayer(None, audio_player)
		player.__class__.current_volume = -1
		
		player.configure_volume()
		
		self.assertTrue(player.__class__.current_volume == 2, "Currenct volume")
		self.assertTrue(player.volume_step == 1, "Correct step")
		
		player.loaded = True
		
		player.__class__.current_volume = 0
		player.volume_up()
		self.assertTrue(player.__class__.current_volume == 1, "Current volume")

		player.__class__.current_volume = 9
		player.volume_up()
		self.assertTrue(player.__class__.current_volume == 10, "Current volume")
		player.volume_up()
		self.assertTrue(player.__class__.current_volume == 10, "Current volume")
		
		player.__class__.current_volume = 2
		player.volume_down()
		self.assertTrue(player.__class__.current_volume == 1, "Current volume")
		player.volume_down()
		self.assertTrue(player.__class__.current_volume == 0, "Current volume")
		player.volume_down()
		self.assertTrue(player.__class__.current_volume == 0, "Current volume")

		player.__class__.current_volume = 2
		self.assertTrue(player.current_volume_percentage() == 20, "Current percentage")
		
		player.__class__.current_volume = 0
		self.assertTrue(player.current_volume_percentage() == 0, "Current percentage")
		
		player.__class__.current_volume = 10
		self.assertTrue(player.current_volume_percentage() == 100, "Current percentage")
		
		player.__class__.current_volume = 2

class FakePlayer(object):
	def max_volume(self):
		return 10;
	
	def set_volume(self, value):
		pass


class MusicHistoryFixture(Fixture):
	def __init__(self):
		self.sl = ServiceLocator()
		self.title = "Music history tests"

	def run(self):
		self.music_history_tests()
		self.send_batches_tests()
	
	def music_history_tests(self):
		ms = []
		for i in range(10):
			ms.append(self.load_music())
		
		repos = MusicHistoryRepository(None)
		repos.load_all_history = lambda: ms
		repos.clear_history = lambda: None
		
		as_service = AudioScrobblerService(None)
		empty = []
		as_service.send = lambda musics:empty.append(1)
		
		m_h = MusicHistory(repos, as_service)
		m_h.send_to_audioscrobbler()
		
		self.assertTrue(len(empty) > 0, "Simple send expected")
		
		for i in range(50):
			ms.append(self.load_music())
		
		empty.pop()
		old_method = m_h.send_batches_to_audioscrobbler
		m_h.send_batches_to_audioscrobbler = lambda musics: None

		m_h.send_to_audioscrobbler()
		
		self.assertTrue(len(empty) == 0, "Batch expected")
		
	def send_batches_tests(self):
		musics = [i for i in range(135)]
		l = []
		m_h = MusicHistory(None, None)
		m_h.send_batch = lambda batch: l.append(len(batch))
		m_h.send_batches_to_audioscrobbler(musics)
		self.assertTrue(l[0] == 50, "Batch 1")
		self.assertTrue(l[1] == 50, "Batch 2")
		self.assertTrue(l[2] == 35, "Batch 3")
	

class AudioScrobblerUserRepositoryFixture(Fixture):
	def __init__(self):
		self.sl = ServiceLocator()
		self.title = "AudioScrobblerUserRepository tests"
		f = open("E:\\as.pwd", "rb")
		self.pwd = f.read().replace(" ", "")
		f.close()

	def run(self):
		u = AudioScrobblerUser("doug_fernando", self.pwd)
		self.sl.user_repository.save(u)
		u2 = self.sl.user_repository.load()
		
		self.assertEquals(u.username, u2.username, "Users")
		self.assertEquals(u.password, u2.password, "Passwords")
	

class MusicListFixture(Fixture):
	def run(self):
		musics = [i for i in range(3)]
		
		ml = MusicList(musics, None, None)
		
		self.assertEquals("1 / 3", ml.current_position_formated(), "Correct first position")
		self.assertTrue(ml.move_previous() == False, "Cannot move back from start")
		self.assertTrue(ml.move_next(), "Can move forward")
		self.assertEquals("2 / 3", ml.current_position_formated(), "Correct sec position")
		self.assertTrue(ml.move_next(), "Can move forward")
		self.assertEquals("3 / 3", ml.current_position_formated(), "Correct last position")
		self.assertTrue(ml.move_next() == False, "Cannot move forward")
		self.assertEquals("3 / 3", ml.current_position_formated(), "Correct last position")
		self.assertTrue(ml.move_previous(), "Can move back")
		self.assertEquals("2 / 3", ml.current_position_formated(), "Correct sec position")
		self.assertTrue(ml.move_previous(), "Can move back")
		self.assertTrue(ml.move_previous() == False, "Cannot move back")
		

class Fixtures(object):
	def __init__(self):
		self.tests = [
			MusicFixture(),
			MusicPlayerFixture(),
			MusicListFixture(),
			MusicHistoryFixture(),
			UserFixture(),
			AudioScrobblerUserRepositoryFixture(),
			MusicHistoryRepositoryFixture(),
			#AudioScrobblerServiceFixture(),
			FileSystemServicesFixture()
			#DbHelper
			#PlayerUI 
		]
		
	
	def run(self):
		for test in self.tests:
			test.run()
		
		appuifw.note(unicode("All %i test suites passed!" % len(self.tests)), "info")
 

##########################################################
######################### PROGRAM ENTRY POINT  
 
if __name__ == '__main__':
	logger = LogFactory.create_for("main")
	try:
		AspyPlayerApplication().run()
	except:
		logger.debug("General error: '%s'" % ''.join(traceback.format_exception(*sys.exc_info())))
	
	
